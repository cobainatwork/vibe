# VibeVoice ASR 實作設計

| | |
|---|---|
| 版本 | 1.0 |
| 日期 | 2026-05-21 |
| 作者 | cobain @ Hualiteq |
| 上游 | https://github.com/microsoft/VibeVoice |
| 狀態 | Draft – 待 review |

---

## 0. 目的與範圍

實作以 **VibeVoice-ASR (7B)** 為核心的離線語音轉錄系統，採用 **兩個彼此獨立的版本** 設計：

- **V-Client**：部署於客戶端的轉錄服務。對外提供 WebSocket（主）與 REST（輔）介面，支援原生 hotwords。
- **V-Trainer**：部署於我方 dev 環境的內部工具集，用上游 LoRA scripts 做 fine-tune，產出 merged checkpoint，**人工攜帶**到客戶端。

兩者**無網路連接**，靠手工搬運 `tar.gz` 模型工件溝通。

### 範圍內（V1）

- 離線轉錄（最長 61 分鐘音/影檔）
- Hotwords（per-request + 持久化 group）
- 中文為主、英文偶現（code-switching）
- LoRA fine-tune 與 merge
- Docker compose 化、可離線安裝
- WebSocket 上傳 + 即時 segment 推送 + REST fallback 撈結果

### 範圍外（明確不做）

- 真正低延遲串流 ASR（VibeVoice 家族無此能力，需換模型，已與使用者確認跳過）
- 多租戶 / OAuth / SSO（單組織內部使用，API key 足夠）
- 自動 retry 失敗任務、自動 alert（避免雪崩；客戶可自行加）
- Prometheus / Grafana（V1 過頭）
- Web UI（Gradio 等）
- 客戶端 fine-tune 能力
- 自動模型部署管線（MLflow / DVC / A/B）
- HTTPS/TLS 終結（由客戶現有反向代理處理）

---

## 1. 系統概觀

```
┌─────────── 我方 dev box (48GB VRAM) ──────────┐    ┌──────── 客戶端 (≥24GB VRAM, Ampere+) ────────┐
│                                                │    │                                              │
│   V-Trainer (CLI 工具集)                        │    │   V-Client (Docker compose)                  │
│                                                │    │                                              │
│   prepare_dataset → lora_finetune              │    │   gateway ── redis ── worker ── vllm        │
│       → eval_wer → merge_lora → package        │    │      │                              │        │
│                                  │             │    │      └──── SQLite ──────────────────┘        │
│                                  ▼             │    │                                              │
│              merged-vN.tar.gz + sha256.txt     │    │   current_model/  ◄──── 手工解壓             │
└──────────────────────────────┬─────────────────┘    └──────────────────▲───────────────────────────┘
                               │                                          │
                               └───────── 手工攜帶 (USB / scp / VPN) ──────┘
```

---

## 2. V-Client 架構

### 2.1 元件與職責

| 元件 | 唯一職責 | 不做什麼 |
|------|---------|---------|
| **gateway** (FastAPI) | HTTP/WS 介面、API key 認證、入隊、查詢、CRUD | 不直接呼叫 vLLM、不操 GPU |
| **worker** (Python + RQ) | 拉 job、ffmpeg、組 prompt、呼叫 vLLM、解析輸出、落地 | 不對外暴露 port |
| **vllm** (vllm/vllm-openai:v0.14.1 + vibevoice plugin) | 純推論 | 不知道 hotword groups、不存資料 |
| **redis** | 佇列 + 任務狀態 pubsub | 不存業務資料 |
| **SQLite** | 結構化資料（jobs, hotword_groups, audit log） | 不存大檔 |
| **Volumes** | 大檔案（uploads, results, db, current_model） | — |

選擇 SQLite 而非 Postgres：客戶端單機部署，worker 是唯一寫入者，Redis 已有 queue，Postgres 多餘。

### 2.2 圖

```
┌─ Docker Compose ─────────────────────────────────────────────┐
│                                                              │
│  ┌─ gateway :8000 ───────────────────────────────────┐       │
│  │  • X-API-Key 認證                                  │       │
│  │  • WS  /v1/transcribe                              │       │
│  │  • GET /v1/jobs/{id}/result   (fallback)           │       │
│  │  • CRUD /v1/hotword-groups                         │       │
│  │  • GET /v1/models/current, /v1/health              │       │
│  └──────────────────┬─────────────────────────────────┘       │
│                     │ enqueue / pubsub                        │
│                     ▼                                         │
│  ┌─ redis ─────────────────────┐                              │
│  │ queue + job:{id} pubsub      │                              │
│  └──────────────┬──────────────┘                              │
│                 │ pop                                          │
│                 ▼                                              │
│  ┌─ worker ──────────────────────────────────────────┐         │
│  │ 1. (video?) ffmpeg → audio.mp3                     │         │
│  │ 2. 讀 hotword_groups + per-request hotwords         │         │
│  │ 3. 合併+dedup+≤200 → context_info                  │         │
│  │ 4. 組 prompt（byte-perfect 對齊 processor）          │         │
│  │ 5. POST vllm /v1/chat/completions (file path 模式) │         │
│  │ 6. SSE 串流 + RepetitionDetector + retry            │         │
│  │ 7. processor.post_process_transcription            │         │
│  │ 8. 落地 results/ + UPDATE jobs + PUBLISH segments   │         │
│  └──────────────┬──────────────────────────────────────┘        │
│                 │ HTTP                                          │
│                 ▼                                              │
│  ┌─ vllm :8001 (loopback only) ──────────────────────┐         │
│  │ /v1/chat/completions, /v1/models                    │         │
│  └──────────────┬──────────────────────────────────────┘        │
│                 │ load                                          │
│                 ▼                                              │
│  Volumes (host):                                              │
│    /opt/vibevoice/current_model/   ← 手工放                   │
│    /opt/vibevoice/uploads/         (worker 寫)                │
│    /opt/vibevoice/results/         (worker 寫)                │
│    /opt/vibevoice/db/vibevoice.db                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 vLLM 啟動參數

依上游 `vllm_plugin/scripts/start_server.py:87-109` 與 `docs/vibevoice-vllm-asr.md:27-37`：

```
vllm serve /opt/vibevoice/current_model \
  --served-model-name vibevoice \
  --trust-remote-code \
  --dtype bfloat16 \
  --max-num-seqs 64 \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.8 \
  --no-enable-prefix-caching \
  --enable-chunked-prefill \
  --chat-template-content-format openai \
  --tensor-parallel-size ${VLLM_TP:-1} \
  --data-parallel-size  ${VLLM_DP:-1} \
  --allowed-local-media-path /app \
  --port 8001
```

`tp/dp` 由客戶硬體決定（24GB 單卡 = 1/1；多卡可調）。

---

## 3. V-Trainer 架構

### 3.1 元件（單一 container + CLI 腳本）

```
┌─ Docker container (vibevoice-trainer) ─────────────────────────┐
│                                                                │
│  腳本（CLI）:                                                    │
│    1) tools/prepare_dataset.py                                  │
│       • raw → {n.mp3, n.json} pairs                            │
│       • 含 customized_context 欄位                              │
│       • 切 train/holdout                                        │
│    2) finetuning-asr/lora_finetune.py（上游原檔，不改）           │
│       torchrun --nproc_per_node=1 lora_finetune.py ...          │
│    3) tools/eval_wer.py                                         │
│       • holdout 算 WER：base vs adapter 對比                     │
│       • 用 jiwer 計算                                            │
│    4) tools/merge_lora.py                                       │
│       • PeftModel.from_pretrained → merge_and_unload            │
│       • save_pretrained → merged/vN/                            │
│    5) tools/package.py                                          │
│       • tar -czf VibeVoice-Model-vN.tar.gz merged/vN/           │
│       • sha256sum > sha256.txt                                  │
│                                                                │
│  Volumes:                                                      │
│    datasets/<corpus>/   base_model/                            │
│    adapters/<run_id>/   merged/<vN>/                            │
│    eval_reports/        shipping/                               │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 訓練資料格式

依上游 `finetuning-asr/README.md:36-60`：

```
toy_dataset/
├── 0.mp3
├── 0.json
├── 1.mp3
├── 1.json
└── ...
```

`*.json` schema：

```json
{
  "audio_duration": 351.73,
  "audio_path": "0.mp3",
  "segments": [
    {"speaker": 0, "text": "...", "start": 0.0, "end": 38.68},
    ...
  ],
  "customized_context": ["專有名詞A", "公司產品B"]
}
```

### 3.3 LoRA 訓練參數（沿用上游預設）

| 參數 | 值 | 出處 |
|------|----|------|
| `--lora_r` | 16 | `lora_finetune.py:74` |
| `--lora_alpha` | 32 | `lora_finetune.py:78` |
| `--lora_dropout` | 0.05 | `lora_finetune.py:82` |
| `--learning_rate` | 1e-4 | `finetuning-asr/README.md:76` |
| `--num_train_epochs` | 3（起始）| `README.md:76` |
| `--per_device_train_batch_size` | 1 | `README.md:76` |
| `--bf16` | true | `README.md:75` |
| `--gradient_checkpointing` | true | 48GB VRAM 必要 |
| Target modules | q/k/v/o/gate/up/down_proj | `lora_finetune.py:359-367` |
| Attention | flash_attention_2 | `lora_finetune.py:413`（需 Ampere+） |
| Audio encoder | frozen | `lora_finetune.py:420-422` |

訓練音檔長度由使用者保證（不寫切片工具）。

---

## 4. 橋樑：模型工件交付

```
[dev box]                                              [客戶端]
merged/v3/                                              
   │                                                   
   │ package.py                                        
   ▼                                                   
shipping/VibeVoice-Model-v3.tar.gz                     
shipping/sha256.txt                                    
   │                                                   
   │ 手工攜帶（USB / scp / VPN）                       
   ▼                                                   
                                                       /opt/vibevoice/staging/v3/
                                                              │ sha256sum -c
                                                              │ ln -snf 切換
                                                              ▼
                                                       /opt/vibevoice/current_model
                                                              │ docker compose
                                                              │   restart vllm
                                                              ▼
                                                       /v1/models/current 確認
```

無服務、無 API、無自動同步——一份 SOP 文件搞定（見 §10.5）。

---

## 5. API 規格（V-Client）

### 5.1 認證

所有端點需 `X-API-Key: <key>` header。Key 列在 `config/api_keys.yaml`，server load 時讀入記憶體；變更需重啟 gateway。

### 5.2 WebSocket（主入口）

**Endpoint**：`/v1/transcribe`

**狀態機**：

```
client                                          server
  │── HTTP UPGRADE + X-API-Key ──────────────►  │
  │  ◄── 101 Switching Protocols ──────────────│
  │                                            │
  │── text: {type:"start", filename?, hotwords?, hotword_group_ids?, output_format?}
  │                                            │
  │  ◄── text: {type:"ready", job_id:"abc"} ───│
  │                                            │
  │── binary: <audio chunk 1>  ────────────────►│
  │── binary: <audio chunk 2>  ────────────────►│
  │                ...                          │
  │  ◄── text: {type:"ack", bytes_received: N}─│   (週期 1MB/次)
  │── binary: <audio chunk N>  ────────────────►│
  │── text: {type:"eof"} ──────────────────────►│
  │                                            │
  │  ◄── text: {type:"transcribing", audio_duration: 351.73}
  │  ◄── text: {type:"segment", data:{start_time, end_time, speaker_id, text}}
  │  ◄── text: {type:"segment", data:{...}}    │
  │              ...                            │
  │  ◄── text: {type:"done", summary:{segments, elapsed_sec}}
  │  ◄── close                                  │
```

**錯誤路徑**：任何時間 server 可推 `{"type":"error", "code":..., "detail":..., "job_id":?}` 並關連線。client 用 `job_id` 走 §5.3 fallback。

**start frame schema**：

```json
{
  "type": "start",
  "filename": "meeting.mp3",          // 可選，純記錄
  "hotwords": "微軟,VibeVoice",         // CSV，可選
  "hotword_group_ids": [2, 5],         // 可選
  "output_format": "json"              // json | srt | vtt，預設 json
}
```

**Hotwords 合併演算法**：

```python
words = uniq(
    flatten([db.get_group_words(gid) for gid in hotword_group_ids])
    + parse_csv(hotwords)
)[:200]
context_info = ",".join(words)
```

**Prompt 組裝**（byte-perfect 對齊 `vibevoice/processor/vibevoice_asr_processor.py:360-364`）：

```python
show_keys = ['Start time', 'End time', 'Speaker ID', 'Content']
if context_info:
    user_suffix = (
        f"This is a {duration:.2f} seconds audio, "
        f"with extra info: {context_info}\n\n"
        f"Please transcribe it with these keys: "
        + ", ".join(show_keys)
    )
else:
    user_suffix = (
        f"This is a {duration:.2f} seconds audio, "
        f"please transcribe it with these keys: "
        + ", ".join(show_keys)
    )
```

System prompt（常數）：`"You are a helpful assistant that transcribes audio input into text output in JSON format."`

### 5.3 REST 端點

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/v1/jobs/{job_id}/result` | `?format=json\|srt\|vtt` | 200 + 對應 Content-Type；404 if not found；410 if expired |
| GET | `/v1/hotword-groups` | — | `[{id, name, words[], created_at, updated_at}]` |
| POST | `/v1/hotword-groups` | `{name, words:["微軟","VibeVoice"]}` | `201 {id, ...}` |
| PUT | `/v1/hotword-groups/{id}` | `{name?, words?}` | `200 {...}` |
| DELETE | `/v1/hotword-groups/{id}` | — | `204` |
| GET | `/v1/models/current` | — | `{name, version, loaded_at}` |
| GET | `/v1/health` | — | `{status, vllm_ready, queue_depth, last_job_finished_at?, disk_usage_pct}` |

### 5.4 錯誤格式

WS 與 REST 共用：

```json
{
  "type": "error",        // 僅 WS frame 有此欄
  "code": "AUDIO_DURATION_OUT_OF_RANGE",
  "detail": "audio 4823.2s exceeds 61min limit",
  "job_id": "abc123"      // 可選
}
```

REST 走 HTTP 4xx/5xx + body（無 `type` 欄）。

### 5.5 限制

- 單檔 ≤ 1GB（可調 `MAX_FILE_SIZE_MB`）
- 音檔長度 0.5s ~ 61min（依模型）
- Hotwords ≤ 200 詞（合併後）
- Queue depth ≤ 100（可調，滿了回 `QUEUE_FULL`）
- WS idle ping timeout 60s
- 結果保留預設 30 天（可調 `RETAIN_RESULT_DAYS`）

### 5.6 支援格式

依 `vllm_plugin/tests/test_api.py:35-43, 59-83`：

- 音檔：`.wav .mp3 .m4a .flac .ogg .opus`
- 影片（需 ffmpeg 抽音）：`.mp4 .m4v .mov .webm .avi .mkv`

---

## 6. 資料流

### 6.1 V-Client 轉錄（每次 WS 連線）

1. WS UPGRADE + X-API-Key 驗證 → gateway 配 `job_id` (UUID)
2. client 送 `start` frame → gateway 建 `uploads/{job_id}/` 目錄
3. client 串流 binary → gateway 寫到 `uploads/{job_id}/upload.bin`（週期 ack）
4. client 送 `eof` → gateway INSERT jobs (status=queued) → RPUSH 進 redis queue
5. worker BLPOP → UPDATE status=running
6. worker：偵測類型，若 video → ffmpeg 抽音 → `uploads/{job_id}/audio.mp3`
7. worker：合併 hotwords → 組 prompt
8. worker：POST vllm `/v1/chat/completions` with `audio_url: file:///app/uploads/{job_id}/audio.mp3`，stream=true
9. worker：SSE 解析 + RepetitionDetector + 必要時 retry（temp 0.2/0.3/0.4，最多 3 次）
10. worker：每 parse 出一段 segment → `PUBLISH job:{id} '{"type":"segment",...}'`
11. gateway WS handler 訂閱 `job:{id}` → forward 給對應 client
12. worker：`processor.post_process_transcription()` → 落地 `results/{job_id}/output.json`（+ srt/vtt 視 output_format）
13. worker：UPDATE status=done → PUBLISH `{"type":"done",...}`
14. gateway forward done → 關 WS
15. 任務完成立即刪 `uploads/{job_id}/`（隱私）

### 6.2 V-Trainer 訓練與交付

1. 工程師收集音檔 + 人工逐字稿
2. `prepare_dataset.py --in raw/ --out datasets/v3/ --holdout 0.1` → mp3+json pairs + train/holdout 切分
3. `torchrun --nproc_per_node=1 lora_finetune.py --model_path microsoft/VibeVoice-ASR --data_dir datasets/v3/train/ --output_dir adapters/v3/ --num_train_epochs 3 --lora_r 16 --bf16 --gradient_checkpointing`
4. `eval_wer.py --base microsoft/VibeVoice-ASR --adapter adapters/v3/ --holdout datasets/v3/holdout/` → 報表
5. 判斷 WER 是否改善；不滿意改 hyperparams 回 step 3
6. `merge_lora.py --base microsoft/VibeVoice-ASR --adapter adapters/v3/ --out merged/v3/`
7. Smoke test：本機起 vLLM 載 `merged/v3/`，跑 fixtures 音檔，眼看品質
8. `package.py --model merged/v3/ --out shipping/VibeVoice-Model-v3.tar.gz`
9. 手工攜帶到客戶端 → 客戶執行 §10.5 SOP

---

## 7. 錯誤處理

| 層級 | 觸發 | 對外 | 內部 |
|------|------|------|------|
| gateway | 無效 API Key | `error: AUTH_FAIL` → close | access log |
| gateway | 檔 > 1GB | `error: FILE_TOO_LARGE` | 拒收 |
| gateway | 不支援格式 | `error: UNSUPPORTED_FORMAT` | — |
| gateway | queue 滿 | `error: QUEUE_FULL, retry_after_sec: 60` | — |
| gateway | client 上傳途中斷 | — | 清 partial、DB `aborted` |
| gateway | client 接結果途中斷 | — | worker 繼續做完，落地，可走 REST fallback |
| gateway | WS idle > 60s | 主動 close | — |
| worker | ffmpeg 失敗 | `error: DECODE_FAILED` | DB failed，留檔備調 |
| worker | duration 範圍外 | `error: AUDIO_DURATION_OUT_OF_RANGE` | 不送 vLLM |
| worker | vLLM timeout | `error: INFERENCE_TIMEOUT` | DB failed，**不**自動重試 |
| worker | vLLM 5xx | `error: INFERENCE_ERROR` | 同上 |
| worker | repetition loop | 內部 silent | 依 `RepetitionDetector` 升溫重試 ≤ 3 次 |
| worker | JSON 解析失敗 | `warning: PARTIAL_PARSE` + segment 用 raw text | 落 raw_text.txt |
| worker | process crash | 連線斷 | Docker restart，job 仍在 redis queue |
| vllm | 啟動 OOM | `/v1/health: vllm_ready=false` | compose 反覆 restart；客戶看 logs |
| vllm | 推論中 OOM | 5xx 回 worker | 同 worker vllm 5xx 路徑 |
| 儲存 | uploads/results > 90% | HTTP 507 / WS `DISK_FULL` | log + 加速 retention |

---

## 8. 資源隔離

| Service | CPU | RAM | GPU | restart |
|---------|-----|-----|-----|---------|
| gateway | 1 | 512MB | — | unless-stopped |
| worker | 4 | 4GB | — | unless-stopped |
| vllm | 4 | 24GB | all（依客戶硬體 `--gpus`）| unless-stopped |
| redis | 0.5 | 256MB | — | unless-stopped |

**單 worker 序列處理**（V1）。vLLM 內部 continuous batching；worker 端 N=1 不爭。

### 保留策略

| 資料 | 預設保留 | env |
|------|---------|-----|
| `uploads/{job_id}/` | 任務完成立刻刪 | `RETAIN_UPLOAD_DAYS=0` |
| `results/{job_id}/` | 30 天 | `RETAIN_RESULT_DAYS=30` |
| `jobs` 表 | 90 天 | `RETAIN_JOB_RECORD_DAYS=90` |

每日 03:00 cron 清理。

---

## 9. 測試策略

### 9.1 金字塔

```
        ┌──────┐
        │ E2E  │  3-5 個（全棧 + 真實 vLLM）
        ├──────┤
        │ 整合  │  15-25 個（gateway+redis+worker, mock vLLM）
        ├──────┤
        │ 單元  │  最多（純函式、無 I/O）
        └──────┘
```

比例目標：單元 70% / 整合 25% / E2E 5%。

### 9.2 必測模組（V-Client）

| 模組 | 必測 |
|------|------|
| `prompt_builder` | byte-perfect 對齊 processor 格式（有/無 hotwords 兩條） |
| `hotword_merger` | groups 合併 + dedup + 上限 200 + 順序穩定 |
| `ws_protocol` | 狀態機正常 + 異常路徑 |
| `sse_parser` + `repetition_detector` | fork 自上游 `test_api_auto_recover.py:126-460`，補單元測試 |
| `result_writer` | json/srt/vtt 三種格式正確 |
| `auth` | API key 合法/錯誤/缺少 |
| `validation` | 檔案大小、副檔名、duration 範圍 |
| `job_repository` | INSERT/UPDATE/SELECT + 並發 |
| `vllm_client` | mock SSE → 解析正確 |
| 整合 | 完整一輪 transcribe（mock vLLM） |
| E2E（真 vLLM）| ① 3 秒中文成功；② hotwords 進 prompt；③ WS 斷後 REST fallback；④ 不支援格式拒絕；⑤ 超長拒絕 |

### 9.3 必測模組（V-Trainer）

| 模組 | 必測 |
|------|------|
| `prepare_dataset` | JSON schema 驗證、壞檔處理、customized_context 攜帶 |
| `eval_wer` | WER 公式（用 jiwer，配 hand-crafted 例子驗）、批次評估 |
| `merge_lora` | merge 後可被 vLLM `--model` 載入（smoke test） |
| `package` | tar 內容齊全、sha256 一致 |

### 9.4 測試 fixtures

打包進 repo `tests/fixtures/audio/`：

- `zh_tw_short.wav`（3-5s 繁中）
- `en_short.wav`（3-5s 英文）
- `mixed_short.wav`（3-5s 中英夾雜）
- `silent.wav`（< 0.5s 拒絕測試）
- `corrupted.mp3`（壞檔測試）
- `tiny_holdout/`（5 對 mp3+json 給 V-Trainer eval_wer 用）

不打包客戶語料與長音檔。

### 9.5 Mock vLLM

`tests/fixtures/fake_vllm.py`：FastAPI app，`POST /v1/chat/completions` 接 streaming request，根據環境變數回放預錄 SSE 序列（含正常 / repetition / 5xx / timeout）。

### 9.6 工具鏈

- pytest + pytest-asyncio + pytest-cov
- testcontainers（自動起 redis）
- httpx（REST client）、websockets（WS client）
- jiwer（WER 計算）

### 9.7 覆蓋率門檻

- 核心模組（`prompt_builder` / `hotword_merger` / `sse_parser`）≥ 90%
- 整體 ≥ 70%
- E2E 不進 commit gate，nightly 或手動觸發

---

## 10. 部署

### 10.1 Images

| Image | 來源 |
|-------|------|
| `vibevoice-app:vN` | 自製：Python 3.10 + FastAPI + ffmpeg + 我們的程式 |
| `vibevoice-trainer:vN` | 自製：CUDA + torch + peft + 訓練腳本 |
| `vllm/vllm-openai:v0.14.1` | 上游官方，掛 `vibevoice_src/` 進去 |
| `redis:7-alpine` | 上游官方 |

`vibevoice-app` 一個 image 兩用，`command:` 區分 gateway/worker。

### 10.2 V-Client docker-compose.yml（節錄）

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  vllm:
    image: vllm/vllm-openai:v0.14.1
    restart: unless-stopped
    ipc: host
    ports: ["127.0.0.1:8001:8001"]
    entrypoint: bash
    command: >
      -c "python3 /app/vllm_plugin/scripts/start_server.py
          --model /opt/vibevoice/current_model
          --port 8001 --tp ${VLLM_TP:-1} --dp ${VLLM_DP:-1}"
    volumes:
      - ./vibevoice_src:/app
      - ./current_model:/opt/vibevoice/current_model
    environment:
      - VIBEVOICE_FFMPEG_MAX_CONCURRENCY=64
      - PYTORCH_ALLOC_CONF=expandable_segments:True
      - VIBEVOICE_MAX_AUDIO_DURATION=3660
    deploy:
      resources:
        reservations:
          devices:
            - {driver: nvidia, count: all, capabilities: [gpu]}
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:8001/v1/models || exit 1"]
      interval: 10s
      retries: 60
      start_period: 5m

  gateway:
    image: vibevoice-app:${APP_TAG}
    restart: unless-stopped
    command: uvicorn gateway.main:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    depends_on:
      redis: {condition: service_healthy}
      vllm:  {condition: service_healthy}
    volumes:
      - ./data/uploads:/app/data/uploads
      - ./data/results:/app/data/results
      - ./data/db:/app/data/db
      - ./config:/app/config:ro
    env_file: .env

  worker:
    image: vibevoice-app:${APP_TAG}
    restart: unless-stopped
    command: python -m worker.main
    depends_on:
      redis: {condition: service_healthy}
      vllm:  {condition: service_healthy}
    volumes:
      - ./data/uploads:/app/data/uploads
      - ./data/results:/app/data/results
      - ./data/db:/app/data/db
      - ./config:/app/config:ro
    env_file: .env
```

### 10.3 V-Trainer docker-compose.yml

```yaml
services:
  trainer:
    image: vibevoice-trainer:${TRAINER_TAG}
    volumes:
      - ./datasets:/work/datasets
      - ./base_model:/work/base_model
      - ./adapters:/work/adapters
      - ./merged:/work/merged
      - ./eval_reports:/work/eval_reports
      - ./shipping:/work/shipping
    deploy:
      resources:
        reservations:
          devices:
            - {driver: nvidia, count: 1, capabilities: [gpu]}
    stdin_open: true
    tty: true
    command: bash
```

工程師：`docker compose run --rm trainer`，進去手動跑 CLI。

### 10.4 客戶端初次安裝 SOP

```bash
# 0) 前置檢查
#    - Docker ≥ 24 + nvidia-container-toolkit
#    - GPU compute capability ≥ 8.0 (Ampere+)
#    - VRAM ≥ 24GB
#    - 磁碟 ≥ 50GB free

tar -xzf VibeVoice-Client-v1.0.tar.gz
cd vibevoice-client

# 1) 載入離線 images
./scripts/load_images.sh

# 2) 放 model
tar -xzf VibeVoice-Model-v1.tar.gz -C ./current_model/
sha256sum -c ./current_model/sha256.txt

# 3) 設定
cp config/api_keys.example.yaml config/api_keys.yaml
$EDITOR config/api_keys.yaml
cp .env.example .env
$EDITOR .env

# 4) 啟動前檢查
./scripts/preflight.sh

# 5) 啟動
docker compose up -d

# 6) 等就緒
./scripts/wait_for_ready.sh   # poll /v1/health 直到 vllm_ready=true（≤ 10 分鐘）

# 7) Smoke test
./scripts/smoke_test.sh
```

### 10.5 客戶端更新模型 SOP

```bash
# 1) 解壓
tar -xzf VibeVoice-Model-v2.tar.gz -C /opt/vibevoice/staging/v2/
sha256sum -c /opt/vibevoice/staging/v2/sha256.txt

# 2) Atomic swap
ln -snf /opt/vibevoice/staging/v2 ./current_model

# 3) 重啟 vLLM
docker compose stop vllm
docker compose up -d vllm
./scripts/wait_for_ready.sh

# 4) 驗證
curl -H "X-API-Key: $KEY" http://localhost:8000/v1/models/current
# {"name": "vibevoice-merged-v2", "version": "v2", "loaded_at": "..."}

# 5) 舊版保留最近 3 版
ls /opt/vibevoice/staging/
```

### 10.6 啟動依賴

```
redis  ─── healthy ──┐
                     ├──► gateway, worker
vllm   ─── healthy ──┘

vLLM 首次啟動 ≈ 2-5 分鐘（讀 model + warmup）。
Gateway 在 vllm 未 ready 時：/v1/health 回 degraded，WS 新連線拒絕。
```

### 10.7 設定檔

```
config/
├── api_keys.yaml          # 多 key 隨選 rotate
└── .env                   # 非密設定：限額、retention、TP/DP
```

不引入外部 secrets manager。

### 10.8 備份

| 路徑 | 頻率 | 方式 |
|------|------|------|
| `data/db/vibevoice.db` | 每日 | `sqlite3 .backup` + gzip + 留 7 份 |
| `data/results/` | 由 retention 控 | 客戶自選外部 backup |
| `config/api_keys.yaml` | 變更時 | 手工，單獨保管 |
| `current_model/` | 不需（golden 在我方） | — |

---

## 11. 取捨摘要

| 議題 | 決定 | 理由 |
|------|------|------|
| 兩個版本拆分 | V-Client 與 V-Trainer 完全獨立 | 客戶端不需訓練；簡化各自架構 |
| LoRA 部署機制 | 訓練 → merge → tar.gz → 手工攜帶 | vLLM plugin 不支援 LoRA 熱載（`model.py:929` 無 SupportsLoRA） |
| Postgres vs SQLite | SQLite | 單機 + 單 writer + Redis 已有 queue |
| vLLM 對外暴露 | loopback only | 攻擊面減少；只有 worker 呼叫 |
| 一個 image 雙用 | gateway/worker 同 image | 維運面積最小 |
| 串流 ASR | 不做 | VibeVoice 無原生 streaming 模型；換模型超出範圍 |
| Worker 自動重試 | 不做 | 避免雪崩；明確錯誤回呼 |
| Audio 傳 vLLM | file path（不是 base64） | 避開 nginx 200MB 上限 |
| Auto-recovery | Fork 上游 `test_api_auto_recover.py` | 不重造輪子 |
| JSON 解析 | 用上游 `post_process_transcription` | 同上 |
| Hotwords 機制 | prompt-embedding（byte-perfect 對齊 processor）| Server 端無 hotword flag；prompt 是唯一管道 |
| Hotwords 上限 | 200 詞合併後 | 避免 prompt 爆長 |
| 監控 | 結構化日誌 + /health；不加 Prometheus | V1 不過度設計，客戶要可擴 |
| 認證 | API Key in header | 單組織內部，OAuth 過頭 |

---

## 附錄 A：上游 source 對照表

| 我方設計細節 | 上游檔案 | 行 |
|------------|---------|----|
| Docker image + 啟動參數 | `docs/vibevoice-vllm-asr.md` | 27-37 |
| vLLM serve 旗標完整列表 | `vllm_plugin/scripts/start_server.py` | 87-109 |
| OpenAI Chat Completions wire format | `vllm_plugin/tests/test_api.py` | 138-180 |
| Hotwords prompt 拼接（測試端）| `vllm_plugin/tests/test_api.py` | 144-148 |
| Hotwords prompt 拼接（processor 端）| `vibevoice/processor/vibevoice_asr_processor.py` | 360-364 |
| System prompt 常數 | `vibevoice/processor/vibevoice_asr_processor.py` | 27 |
| 音檔上限 env | `vllm_plugin/inputs.py` | 20 |
| 支援音/影格式 | `vllm_plugin/tests/test_api.py` | 35-43, 59-83 |
| 影片→ffmpeg 抽音 | `vllm_plugin/tests/test_api.py` | 75-83 |
| Audio token 展開 | `vllm_plugin/model.py` | 890-896 |
| 61 分鐘上限常數 | `vllm_plugin/model.py` | 587 |
| nginx body 限制 200MB | `vllm_plugin/scripts/start_server.py` | 179 |
| LoRA 訓練超參數 | `finetuning-asr/lora_finetune.py` | 73-83 |
| LoRA target modules | `finetuning-asr/lora_finetune.py` | 359-367 |
| Audio encoder frozen | `finetuning-asr/lora_finetune.py` | 420-422 |
| Flash attention | `finetuning-asr/lora_finetune.py` | 413 |
| Training data JSON schema | `finetuning-asr/README.md` | 36-60 |
| Merge 範例 | `finetuning-asr/README.md` | 140-154 |
| RepetitionDetector + retry | `vllm_plugin/tests/test_api_auto_recover.py` | 126-460 |
| `post_process_transcription` | `vibevoice/processor/vibevoice_asr_processor.py` | 490-565 |
| vLLM plugin 註冊 | `pyproject.toml` | 47-48 |
| 模型不支援 SupportsLoRA | `vllm_plugin/model.py` | 929 |
| Python ≥ 3.10、transformers 版本 | `pyproject.toml` | 13, 21 |

---

## 附錄 B：依賴清單（V-Client app）

僅列我們自寫程式的直接依賴；其餘依賴跟上游 `pyproject.toml` 對齊。

| Package | 用途 |
|---------|------|
| fastapi | HTTP + WS server |
| uvicorn[standard] | ASGI server |
| websockets | WS client (測試用) |
| rq | 任務佇列 |
| redis | rq + pubsub |
| httpx | 呼叫 vLLM |
| pydub / av | 音檔處理輔助 |
| sqlite3（stdlib） | 持久化 |
| pyyaml | config 讀取 |
| pytest, pytest-asyncio, pytest-cov | 測試 |
| testcontainers | 整合測試 |
| jiwer | WER（V-Trainer） |

---

## 附錄 C：V1 完成定義（Done = ?）

- [ ] V-Client docker compose up -d 之後，從 fixture 音檔 WS 轉錄成功，輸出 JSON 含 segments
- [ ] Hotwords（per-request + group）正確進 prompt（log 驗證 byte-perfect 對齊 processor 格式）
- [ ] WS 中斷後 REST fallback 撈得到結果
- [ ] 全部 9.2 + 9.3 測試項通過；覆蓋率達門檻
- [ ] V-Trainer 完整跑通 `prepare_dataset → lora_finetune → eval_wer → merge_lora → package`
- [ ] Merged checkpoint 從 V-Trainer 攜帶到 V-Client、SOP 走完、`/v1/models/current` 回新版
- [ ] 客戶端初次安裝 SOP 與更新模型 SOP 由非 dev 工程師驗證可走通
- [ ] 所有錯誤路徑（§7 表）至少 1 個測試覆蓋

---

## 附錄 D：未來工作（P2+）

- 真正低延遲串流：另接 Whisper-streaming / Parakeet RNN-T；獨立 stack
- Prometheus / Grafana metrics endpoint
- 多 worker 副本（共用 Redis queue）；橫向擴展
- Webhook 通知 vLLM crash / queue 滿
- Gradio 評估 UI（V-Trainer）
- 自動 retention 看板
- MLflow 實驗追蹤（V-Trainer 訓練量大時）
