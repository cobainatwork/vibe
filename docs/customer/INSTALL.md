# VibeVoice Client 安裝手冊

> V-Client 部署 SOP。閱讀對象：客戶端系統管理員。

## 前置條件

- **作業系統**：Linux (Ubuntu 22.04 LTS 以上推薦)
- **Docker**：版本 24 以上
- **NVIDIA Container Toolkit**：已安裝並能跑 GPU container
- **GPU**：NVIDIA，compute capability 8.0+ (Ampere 之後)，VRAM ≥ 24GB
- **磁碟空間**：≥ 60GB（含 Docker images、模型檔）
- **網路**：需可連 `hub.docker.com` 與 `github.com`（首次安裝下載 image 與 source）

驗證指令：

    docker --version
    nvidia-smi
    df -BG .

## 步驟 1：解壓部署包

    tar -xzf VibeVoice-Client-v0.1.0.tar.gz
    cd VibeVoice-Client-v0.1.0

## 步驟 2：拉取上游 VibeVoice source

vLLM container 內需掛載 microsoft/VibeVoice 的 Python 套件。執行：

    ./scripts/clone_upstream.sh

完成後會在當前目錄出現 `vibevoice_src/`，約 12 MB。

## 步驟 3：設定 API Key

    cp config/api_keys.example.yaml config/api_keys.yaml
    nano config/api_keys.yaml   # 把 key 改成長隨機字串

格式：

```yaml
- name: ops
  key: <你的長隨機字串>
```

可加多筆 key，按用途命名。

## 步驟 4：設定環境變數

    cp .env.example .env
    nano .env

關鍵欄位：
- `VLLM_TP`、`VLLM_DP`：依 GPU 數量調整（單卡用 1/1；4 卡 dp=4）
- `MAX_FILE_SIZE_MB`：客戶單檔上限（預設 1024）
- `RETAIN_RESULT_DAYS`：轉錄結果保留天數（預設 30）

## 步驟 5：放置模型

把我方提供的 `VibeVoice-Model-vN.tar.gz` 解壓到 `current_model/`：

    tar -xzf /path/to/VibeVoice-Model-vN.tar.gz -C ./current_model/
    sha256sum -c ./current_model/sha256.txt

執行前必須驗 sha256。

## 步驟 6：前置檢查

    ./scripts/preflight.sh

通過後再繼續。

## 步驟 7：啟動服務

    docker compose up -d --build

`--build` 會建出 `vibevoice-app:0.1.0` image（首次約 3-5 分鐘）。

## 步驟 8：等待 vLLM 就緒

    ./scripts/wait_for_ready.sh

首次啟動 vLLM 需 2-5 分鐘載入模型 + warmup。

## 步驟 9：Smoke test

    ./scripts/smoke_test.sh

預期看到 `/v1/health` 回 `vllm_ready: true`，`/v1/models/current` 回模型版本，WS 轉錄 3 秒音檔成功。

## 一般操作

### 查看日誌

    docker compose logs -f gateway worker vllm

### 重啟單一服務

    docker compose restart gateway

### 停止服務

    docker compose down

### 更新模型

    # 1. 解壓新版到 staging
    tar -xzf VibeVoice-Model-v2.tar.gz -C /opt/vibevoice/staging/v2/
    sha256sum -c /opt/vibevoice/staging/v2/sha256.txt

    # 2. atomic swap
    ln -snf /opt/vibevoice/staging/v2 ./current_model

    # 3. 重啟 vLLM
    docker compose stop vllm
    docker compose up -d vllm
    ./scripts/wait_for_ready.sh

    # 4. 驗證
    curl -H "X-API-Key: $KEY" http://localhost:8000/v1/models/current

舊版保留最近 3 版，更舊的人工刪。

## 故障排查

| 症狀 | 排查 |
|------|------|
| vLLM container 反覆 restart | `docker logs vibevoice-vllm-1`；多半是 CUDA OOM，調低 `--gpu-memory-utilization` 或縮 `--max-num-seqs` |
| `/v1/health` 持續 `vllm_ready: false` | 等 5 分鐘；若仍 false 看 vLLM 日誌；確認 GPU 可見 (`docker compose exec vllm nvidia-smi`) |
| `error: QUEUE_FULL` | 工人忙；等或加 worker 副本 |
| `error: DECODE_FAILED` | 音檔格式不支援或損毀；確認檔副檔名在 wav/mp3/m4a/flac/ogg/opus/mp4/m4v/mov/webm/avi/mkv |
| WebSocket 斷線 | client 用 fallback：`GET /v1/jobs/{job_id}/result?format=json` |

## API 速查

| 端點 | 用途 |
|------|------|
| `WS /v1/transcribe` | 上傳音檔 + 接收轉錄結果（主入口） |
| `GET /v1/jobs/{job_id}/result?format=json\|srt\|vtt` | WS 斷線後撈結果 |
| `GET/POST/PUT/DELETE /v1/hotword-groups` | hotword 群組管理 |
| `GET /v1/models/current` | 目前載入模型版本 |
| `GET /v1/health` | 健康檢查 |

所有 HTTP/WS 請求需附 header `X-API-Key: <你的 key>`。

## 支援

問題請聯絡你的部署窗口。日誌與設定請打包：

    docker compose logs > logs.txt
    cat config/api_keys.yaml | sed 's/key: .*/key: REDACTED/' > config_redacted.yaml
    cat .env

提供以上 + 故障時間點。
