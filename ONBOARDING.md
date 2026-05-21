# VibeVoice ASR Client — Project Onboarding

> Dense state-of-the-project doc. Read this instead of replaying chat history.

## What this is

On-prem deployable VibeVoice ASR (speech-to-text) service. Customer side runs a 4-container docker-compose stack; our side will run a separate fine-tuning workbench (V-Trainer, not built yet).

- **Upstream**: https://github.com/microsoft/VibeVoice (cloned at `vibevoice_src/`, gitignored)
- **Our repo**: https://github.com/cobainatwork/vibe (private, `main` branch, 30 commits)
- **Working dir**: `/Users/cobain/project/vibe_asr`

## Architecture (V-Client, only thing built so far)

```
client ─WS─► gateway (FastAPI) ──► redis (queue) ──► worker (RQ) ──HTTP──► vllm (vibevoice plugin)
                │                                       │                       │
                └──── SQLite (jobs, hotword_groups) ────┘                 current_model/ (mounted)
```

- **Auth**: `X-API-Key` header, keys in `config/api_keys.yaml`
- **WS protocol**: client sends `start` JSON → server `ready` → client streams binary audio → `eof` → server forwards `segment`/`done`/`error` events
- **Hotwords**: per-request CSV + persistent groups, merged and embedded byte-perfect in prompt (matches upstream processor `vibevoice_asr_processor.py:360-364`)
- **vLLM**: official `vllm/vllm-openai:v0.14.1` image + `vibevoice_src/vllm_plugin/scripts/start_server.py`. Audio passed by file path (avoid base64 / 200MB nginx limit). RepetitionDetector forked from upstream `test_api_auto_recover.py` for long-audio loop recovery.

## Status

- **30 commits** on `main`, pushed to GitHub
- **91 tests** passing (unit + integration; e2e skipped without real vLLM)
- **Lint clean**: ruff + bandit + mypy all green via `./scripts/lint_all.sh`
- **Bundle ready**: `dist/VibeVoice-Client-v0.1.0.tar.gz` (~26KB, lightweight online install)
- **Customer docs**: `docs/customer/INSTALL.md` (繁中 9-step SOP)

## Key documents (read in this order if onboarding)

1. **`docs/superpowers/specs/2026-05-21-vibevoice-impl-design.md`** — full design spec (11 chapters, ~830 lines, contains upstream source line refs)
2. **`docs/superpowers/plans/2026-05-21-v-client.md`** — implementation plan (27 tasks, all done)
3. **`docs/superpowers/specs/2026-05-21-clean-code-audit.md`** — code quality audit (14 fixed, 10 deferred)
4. **`docs/customer/INSTALL.md`** — customer-side deployment SOP

## Resume points (open work)

All tracked as GitHub issues on `cobainatwork/vibe`:

| # | Title | Source | Effort |
|---|-------|--------|--------|
| [#1](https://github.com/cobainatwork/vibe/issues/1) | Async redis in handlers | audit C-1, C-2 | ~1hr |
| [#2](https://github.com/cobainatwork/vibe/issues/2) | Decompose ws_transcribe | audit C-6 | ~2hr |
| [#3](https://github.com/cobainatwork/vibe/issues/3) | Retention cron | spec §8 | ~1hr |
| [#4](https://github.com/cobainatwork/vibe/issues/4) | Minor cleanup (m-1 ~ m-7) | audit | opportunistic |
| [#5](https://github.com/cobainatwork/vibe/issues/5) | GitHub Actions CI | — | ~1hr |
| [#6](https://github.com/cobainatwork/vibe/issues/6) | V-Trainer (Plan-B) | spec §3 | 1-2 days |
| [#7](https://github.com/cobainatwork/vibe/issues/7) | E2E with real vLLM | needs GPU | varies |

## Project conventions (must follow)

- **Python tooling**: `uv` only (no plain pip, no pyenv). `uv venv --python 3.11`, `uv pip install -e ".[dev]"`, `uv run pytest …`. Python source in `src/` with editable install (no `PYTHONPATH=src` needed).
- **Shell commands**: each command is its own Bash invocation. **No `&&` or `;` chains**. (User preference.)
- **Commits**: `feat()`/`fix()`/`chore()`/`docs()`/`test()` conventional commits. Don't amend; always new commit.
- **Prompt strings**: the strings in `src/shared/prompt_builder.py` must remain byte-perfect with upstream `vibevoice/processor/vibevoice_asr_processor.py:360-364` — they're what the model was trained on. Do not "improve" them.
- **vLLM + LoRA**: the upstream plugin does NOT implement `SupportsLoRA`. Fine-tuned adapters must be `merge_and_unload`'d into a full checkpoint, then served as a new model (no hot-swap).
- **Streaming ASR**: VibeVoice has no streaming-native ASR model. We explicitly do not support live transcription. WS is for offline upload + segment-push.

## Layout

```
.
├── docs/
│   ├── customer/          ← what we ship: README.md, INSTALL.md (繁中)
│   └── superpowers/       ← internal: specs/, plans/
├── src/
│   ├── shared/            ← config, auth, db, validation, prompt_builder, hotword_merger, result_writer, error_codes, repositories/
│   ├── gateway/           ← FastAPI app: main, rest_*, ws_transcribe, upload_writer
│   └── worker/            ← RQ worker: tasks/transcribe, sse_parser, repetition_detector, vllm_client, audio_normalizer, output_parser
├── tests/
│   ├── unit/              ← ~80 unit tests
│   ├── integration/       ← ~10 integration (need redis on localhost:6379)
│   └── e2e/               ← real-vLLM tests (manually triggered, currently skipped)
├── scripts/
│   ├── clone_upstream.sh  ← pulls microsoft/VibeVoice into vibevoice_src/
│   ├── preflight.sh       ← customer-side env check
│   ├── wait_for_ready.sh  ← poll /v1/health until vllm_ready
│   ├── smoke_test.sh      ← WS transcribe verification
│   ├── lint_all.sh        ← ruff + bandit + mypy + pytest one-shot
│   └── build_bundle.sh    ← produces dist/VibeVoice-Client-v0.1.0.tar.gz
├── config/api_keys.example.yaml
├── Dockerfile.app         ← gateway+worker shared image (Python 3.11-slim + ffmpeg)
├── docker-compose.yml     ← 4 services: redis, vllm, gateway, worker
├── pyproject.toml         ← Python 3.10+, ruff/bandit/mypy in dev deps
├── .env.example
├── .cache/                ← gitignored, contains VibeVoice clone used during research
└── current_model/         ← mounted by vllm; customer places merged checkpoint here
```

## Quick start (developer)

```bash
# Install (one-time)
uv venv --python 3.11
uv pip install -e ".[dev]"
./scripts/clone_upstream.sh

# Lint + test
./scripts/lint_all.sh

# Build customer bundle
./scripts/build_bundle.sh
```

For redis (integration tests):
```bash
docker run -d --rm --name redis-test -p 6379:6379 redis:7-alpine
```

## Quick start (customer)

See `docs/customer/INSTALL.md`. Summary:
```bash
tar -xzf VibeVoice-Client-v0.1.0.tar.gz
cd VibeVoice-Client-v0.1.0
./scripts/clone_upstream.sh
cp config/api_keys.example.yaml config/api_keys.yaml && nano ...
cp .env.example .env
tar -xzf VibeVoice-Model-vN.tar.gz -C ./current_model/
./scripts/preflight.sh
docker compose up -d --build
./scripts/wait_for_ready.sh
./scripts/smoke_test.sh
```

## Tools used during build

System (host):
- macOS, uv 0.11.15, Python 3.11.15, ffmpeg 8.1.1
- Docker 29.4.0
- git 2.50.1

Python (in dev venv):
- fastapi, uvicorn, websockets, rq, redis, httpx, pyyaml, python-multipart
- pytest, pytest-asyncio, pytest-cov, testcontainers, ruff, bandit, mypy

## Out of scope (decided NOT to do at V1)

- Real-time / low-latency streaming ASR (model architecture limitation)
- Multi-tenant auth / OAuth (API key sufficient for internal use)
- Prometheus/Grafana metrics endpoint (defer)
- Webhook alerting on vLLM crash (defer)
- HTTPS/TLS termination (assume customer reverse proxy)
- Auto-deploy pipeline from V-Trainer → V-Client (manual SOP per spec §4)
- Customer-side fine-tuning capability (V-Trainer is internal only)

## How to continue

- **Implementation work**: pick an open issue, follow its acceptance criteria.
- **Big new features**: invoke `superpowers:brainstorming` skill → `writing-plans` → `subagent-driven-development` (same workflow that built Plan-A).
- **Code review**: `./scripts/lint_all.sh` then look at the diff. CI not set up yet (issue #5).
- **Customer install verification**: use the bundle in `dist/`, exercise on a Linux box with GPU.
