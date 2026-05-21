# Clean Code Audit — V-Client (`src/`)

**Date:** 2026-05-21  
**Scope:** `src/shared/`, `src/gateway/`, `src/worker/` (all `.py` files)  
**Standard:** Robert C. Martin, *Clean Code*  
**Total findings:** 8 Critical · 9 Important · 7 Minor

## Status (commit `eb01c25`)

**Fixed in clean-code sweep (14 items)**: C-3, C-4, C-5, C-7, C-8, I-1, I-2, I-3, I-4, I-5, I-6, I-7, I-8, I-9.

**Deferred to V1.1** (with reasons):

| # | Why deferred |
|---|---|
| **C-1** | Sync redis in `rest_health.py` async handler. Real but minor impact at V1 scale (single-org internal, low concurrency). Convert to `redis.asyncio` later. |
| **C-2** | Sync redis in `ws_transcribe.py` async handler (queue-depth check + RQ enqueue). Same reasoning — defer; if load grows, refactor with `aioredis` + `run_in_executor` per audit. |
| **C-6** | `ws_transcribe()` 198-line function decomposition into 4 helpers. Significant refactor; do in dedicated PR to avoid touch-conflict with current sweep. |
| **m-1 to m-7** | All Minor: naming, MIME type, atomicity, hard-coded path, type signature. Pick up opportunistically when touching nearby code. |

---

## Critical (should fix now)

### C-1 · `rest_health.py:28` — Synchronous Redis client blocks the async event loop

```python
# BAD — blocks the thread pool and starves other coroutines
r = redis.from_url(cfg.redis_url)
queue_depth = r.llen("rq:queue:transcribe")
```

`rest_health.py` is an `async def` FastAPI handler. `redis.from_url` returns a **synchronous** client; calling `.llen()` inside an async handler blocks the event loop thread for the entire round-trip latency. Under load this serialises all concurrent requests.

**Fix:** replace with `redis.asyncio`:

```python
import redis.asyncio as aioredis

# inside health():
try:
    ar = aioredis.from_url(cfg.redis_url, socket_connect_timeout=2)
    queue_depth = await ar.llen("rq:queue:transcribe")
    await ar.aclose()
except Exception:
    pass
```

---

### C-2 · `ws_transcribe.py:73,169` — Two more synchronous Redis calls inside an async WebSocket handler

```python
_depth_r = SyncRedis.from_url(cfg.redis_url, socket_connect_timeout=2)
queue_depth = _depth_r.llen("rq:queue:transcribe")   # line 75

enqueue_r = SyncRedis.from_url(cfg.redis_url, socket_connect_timeout=2)
queue = rq.Queue("transcribe", connection=enqueue_r) # line 172
```

The RQ enqueue call (line 172) is on the hot path: every WebSocket transcription blocks the event loop while waiting for Redis. The queue-depth check (line 75) is best-effort but still harmful under load.

**Fix for queue-depth check:** use `aioredis` as in C-1.  
**Fix for RQ enqueue:** RQ requires a sync client. Offload to a thread:

```python
import asyncio

def _enqueue_sync(redis_url: str, job_id: str) -> None:
    conn = SyncRedis.from_url(redis_url, socket_connect_timeout=2)
    try:
        rq.Queue("transcribe", connection=conn).enqueue(
            "worker.tasks.transcribe.transcribe_job",
            job_id=job_id,
            job_timeout=3600 * 2,
        )
    finally:
        conn.close()

await asyncio.get_event_loop().run_in_executor(
    None, _enqueue_sync, cfg.redis_url, job_id
)
```

---

### C-3 · `tasks/transcribe.py:146` — Calling a private method (`_check_repetition`) from outside the class

```python
detector.text = accumulated + new_text         # line 145  — mutates private state
is_loop, good_end = detector._check_repetition()  # line 146 — calls private method
```

This breaks encapsulation (Law of Demeter), couples transcribe.py to the internal implementation of `RepetitionDetector`, and circumvents the public `add_text()` API that already does both operations together:

```python
def add_text(self, new_text: str) -> tuple[bool, int]:
    self.text += new_text
    return self._check_repetition()
```

**Fix:** replace the two lines with the public API:

```python
is_loop, good_end = detector.add_text(new_text)
```

Remove the manual `detector.text = ...` assignment entirely.

---

### C-4 · `ws_transcribe.py:112` and `tasks/transcribe.py:198` — `import shutil` inside function bodies

```python
# ws_transcribe.py:112 — inside the binary-receive while loop
import shutil
shutil.rmtree(upload_target.parent, ignore_errors=True)

# tasks/transcribe.py:198 — inside transcribe_job(), inside an if-block
import shutil
shutil.rmtree(job_upload_dir, ignore_errors=True)
```

`import` inside a function body is a code smell: it hides dependencies, re-executes the import machinery on every call (mitigated by the module cache but still bad practice), and makes the dependency graph opaque to tooling and reviewers.

**Fix:** move both to module-level imports at the top of each file.

---

### C-5 · `shared/validation.py:26,39,46` — Deferred `from shared.error_codes import ...` inside function bodies

```python
def check_filename_ext(filename: str) -> tuple[str, str]:
    from shared.error_codes import UNSUPPORTED_FORMAT   # line 26

def check_file_size_mb(size_mb: float, *, max_mb: int) -> None:
    from shared.error_codes import FILE_TOO_LARGE       # line 39

def check_audio_duration_sec(seconds: float) -> None:
    from shared.error_codes import AUDIO_DURATION_OUT_OF_RANGE  # line 46
```

Three separate deferred imports of constants that never cause circular-import issues. This pattern obscures the module's true dependencies and is inconsistent with every other file in the codebase.

**Fix:** hoist all three to module-level:

```python
from shared.error_codes import (
    AUDIO_DURATION_OUT_OF_RANGE,
    FILE_TOO_LARGE,
    UNSUPPORTED_FORMAT,
)
```

---

### C-6 · `ws_transcribe.py:31` — 228-line function doing 5 distinct things (SRP violation)

`ws_transcribe` is a single `async def` of 198 body lines that handles:
1. Auth verification
2. Parsing the `start` frame
3. Receiving binary chunks + EOF
4. Enqueueing to RQ
5. Subscribing to pubsub and forwarding events

This makes the function impossible to test in isolation, hard to read (no abstraction layers), and fragile — changing enqueue logic requires reading through upload logic and vice versa.

**Fix:** extract four private helpers, leaving the top-level handler as a coordinator:

```python
async def _receive_start_frame(ws, timeout) -> dict | None: ...
async def _receive_upload(ws, writer, timeout) -> bool: ...
async def _enqueue_job(redis_url, job_id) -> None: ...
async def _forward_events(ws, redis_url, job_id) -> None: ...
```

Each is ≤30 lines, independently testable, and the top-level function becomes a readable state-machine narrative.

---

### C-7 · `tasks/transcribe.py:107` — N+1 query pattern when loading hotword groups

```python
group_ids = [int(x) for x in parse_csv(job.hotword_group_ids_csv)]
group_words = [get_group_words(conn, [gid]) for gid in group_ids]  # N queries
```

For each group ID a separate `SELECT words_csv FROM hotword_groups WHERE id IN (?)` query is issued. `get_group_words` already accepts a `list[int]` for batch retrieval, but it is called in a list comprehension with a single-element list.

**Fix:** pass all IDs in one call:

```python
group_ids = [int(x) for x in parse_csv(job.hotword_group_ids_csv)]
all_group_words = get_group_words(conn, group_ids)   # 1 query, returns flat list
merged_words = merge_hotwords([all_group_words], per_request, max_words=MAX_HOTWORDS)
```

Note: `merge_hotwords` expects `list[list[str]]`; wrapping in `[all_group_words]` preserves the signature contract.

---

### C-8 · `ws_transcribe.py:179` / `ws_transcribe.py:222,227` — Swallowed exceptions with no log or re-raise

```python
except Exception as exc:                               # line 179
    log.warning("Failed to enqueue job %s: %s", ...)  # OK — logged

except Exception as exc:                               # line 222
    log.warning("Pubsub setup failed for job %s: %s", ...)  # OK

try:                                                   # line 225-228
    await websocket.close()
except Exception:                                      # SILENT — no log, no context
    pass
```

The final bare `except Exception: pass` is harmless here (close on already-closed socket), but combined with the pattern of silent swallowing throughout `rest_health.py` (lines 22, 30, 37), it trains readers to expect hidden failures. `rest_health.py` swallows every failure branch with no logging, making it impossible to detect misconfigurations.

**Fix for `rest_health.py`** — add debug-level logging inside each `except`:

```python
except Exception as exc:
    log.debug("vLLM health check failed: %s", exc)

except Exception as exc:
    log.debug("Redis health check failed: %s", exc)
```

**Fix for `ws_transcribe.py:227`** — at minimum use `log.debug`:

```python
except Exception as exc:
    log.debug("WebSocket close error (job %s): %s", job_id, exc)
```

---

## Important (good to fix in this sweep)

### I-1 · `shared/repositories/hotword_repository.py:9` and `job_repository.py:9` — Duplicated `_now()` utility

Both repository modules define an identical private helper:

```python
def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
```

DRY violation. Any change (e.g., switching to `datetime.now(UTC)` in Python 3.11+) must be made in two places.

**Fix:** extract to `shared/db.py` (already imported by both repositories) or a new `shared/_utils.py`:

```python
# shared/db.py  (or shared/_utils.py)
import datetime as dt

def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
```

Import in both repositories: `from shared.db import utc_now_iso`.

---

### I-2 · `audio_normalizer.py:9` — Unnecessary alias `VIDEO_EXT_SET = VIDEO_EXTS`

```python
from shared.validation import VIDEO_EXTS

VIDEO_EXT_SET = VIDEO_EXTS  # alias
```

The alias adds zero value and creates two names for the same object in the same module. `is_video_file` only uses `VIDEO_EXT_SET`.

**Fix:** remove the alias; use `VIDEO_EXTS` directly:

```python
from shared.validation import VIDEO_EXTS

def is_video_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTS
```

---

### I-3 · `vllm_client.py:63-66` — Redundant conditional dead code

```python
if resp.status_code >= 500:
    raise RuntimeError(f"vLLM {resp.status_code}: {resp.read()[:500]}")
if resp.status_code >= 400:
    raise RuntimeError(f"vLLM {resp.status_code}: {resp.read()[:500]}")
```

The `>= 500` branch is unreachable: any status ≥ 500 also satisfies `>= 400`, and `>= 500` is evaluated first. Both branches produce the same exception with identical message format.

**Fix:** collapse to one check:

```python
if resp.status_code >= 400:
    raise RuntimeError(f"vLLM {resp.status_code}: {resp.read()[:500]}")
```

---

### I-4 · `gateway/main.py:38-42` — Imports inside function body (router imports)

```python
def create_app() -> FastAPI:
    ...
    from gateway.rest_health import router as health_router
    from gateway.rest_models import router as models_router
    from gateway.rest_hotwords import router as hotwords_router
    from gateway.rest_jobs import router as jobs_router
    from gateway.ws_transcribe import router as ws_router
```

The comment above them says "Routes" suggesting the intent was to group them, but they are deferred imports, not just grouping. The circular-import concern that motivates this pattern does not exist here — none of these modules import from `gateway.main`.

**Fix:** hoist to module-level imports:

```python
from gateway.rest_health import router as health_router
from gateway.rest_hotwords import router as hotwords_router
from gateway.rest_jobs import router as jobs_router
from gateway.rest_models import router as models_router
from gateway.ws_transcribe import router as ws_router
```

---

### I-5 · `hotword_repository.py:65,89` — Duplicated `HotwordGroup(...)` construction

`get_group` and `list_groups` both inline a five-argument `HotwordGroup(...)` constructor from a `sqlite3.Row`:

```python
# get_group (line 65)
return HotwordGroup(
    id=row["id"], name=row["name"],
    words=_deserialize_words(row["words_csv"]),
    created_at=row["created_at"], updated_at=row["updated_at"],
)

# list_groups (line 89)
HotwordGroup(
    id=r["id"], name=r["name"],
    words=_deserialize_words(r["words_csv"]),
    created_at=r["created_at"], updated_at=r["updated_at"],
)
```

**Fix:** add a `from_row` classmethod (mirrors `Job.from_row` already present in `job_repository.py`):

```python
@classmethod
def from_row(cls, row: sqlite3.Row) -> "HotwordGroup":
    return cls(
        id=row["id"], name=row["name"],
        words=_deserialize_words(row["words_csv"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )
```

---

### I-6 · `rest_hotwords.py:25` — Missing type hints on `_serialize`

```python
def _serialize(g) -> dict:
```

Parameter `g` has no type annotation. This is the only untyped function parameter in the entire gateway layer.

**Fix:**

```python
from shared.repositories.hotword_repository import HotwordGroup

def _serialize(g: HotwordGroup) -> dict:
```

---

### I-7 · `ws_transcribe.py:96` — Magic constant defined inside handler body instead of module-level

```python
ACK_THRESHOLD = 1024 * 1024  # 1MB
```

This constant is defined inside `ws_transcribe()` on every call. Constants belong at module level.

**Fix:** move to module scope:

```python
_ACK_THRESHOLD_BYTES = 1024 * 1024  # 1 MB: send ack every time this much is received
```

---

### I-8 · `gateway/main.py:22-35` — Auth middleware comment is misleading (disinformation)

```python
# Health is public-ish but we still gate to be uniform; spec §5 says all need auth
if request.url.path == "/v1/health" and request.headers.get("x-api-key"):
    # allow with valid key only
    pass
```

The `if` branch does **nothing** (`pass`) and then falls through to `verify_api_key` anyway. The comment implies health has special treatment, but the code path is identical to every other request. This is misleading noise that will confuse future maintainers.

**Fix:** remove the dead branch entirely:

```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    try:
        verify_api_key(request.headers.get("x-api-key"), cfg.api_keys)
    except AuthError as e:
        return JSONResponse(
            {"error": "AUTH_FAIL", "detail": str(e)},
            status_code=401,
        )
    return await call_next(request)
```

---

### I-9 · `ws_transcribe.py:73,169` and `rest_health.py:29` — Magic string `"rq:queue:transcribe"` duplicated across files

The Redis queue key literal appears in three places:

- `rest_health.py:29`
- `ws_transcribe.py:75`
- `worker/main.py:26` (queue name `"transcribe"` which RQ renders as `rq:queue:transcribe`)

**Fix:** define a single constant in a shared location:

```python
# shared/config.py or a new shared/constants.py
TRANSCRIBE_QUEUE_NAME = "transcribe"
TRANSCRIBE_QUEUE_REDIS_KEY = f"rq:queue:{TRANSCRIBE_QUEUE_NAME}"
```

---

## Minor (note, defer)

### m-1 · `tasks/transcribe.py:121` — Inline arithmetic in hot-path loop with stale comment

```python
temperature = 0.0 if retry == 0 else 0.1 + 0.1 * retry  # 0.2/0.3/0.4
```

The comment `0.2/0.3/0.4` is correct (retry=1→0.2, retry=2→0.3, retry=3→0.4) but is fragile — change `MAX_RETRIES` and the comment becomes wrong. An intent-revealing named function makes the formula self-documenting.

**Fix:**

```python
def _retry_temperature(retry: int) -> float:
    """First attempt uses greedy decoding; retries add progressive randomness."""
    return 0.0 if retry == 0 else 0.1 + 0.1 * retry
```

---

### m-2 · `hotword_repository.py:98-114` — `update_group` read-then-write without transaction

```python
existing = get_group(conn, group_id)    # SELECT
if not existing:
    raise GroupNotFoundError(group_id)
...
conn.execute("UPDATE ...")              # UPDATE
conn.commit()
```

A concurrent DELETE between the SELECT and UPDATE would silently update 0 rows. The `if cur.rowcount == 0` guard used in `delete_group` is absent here.

**Fix (minimal):** check `cur.rowcount` after update:

```python
cur = conn.execute("UPDATE hotword_groups SET ... WHERE id=?", (..., group_id))
conn.commit()
if cur.rowcount == 0:
    raise GroupNotFoundError(group_id)
```

This also removes the extra SELECT on the happy path.

---

### m-3 · `rest_jobs.py:37` — Non-standard MIME type `text/srt`

```python
media = "text/srt" if format == "srt" else "text/vtt"
```

`text/srt` is not a registered IANA MIME type. The correct type is `application/x-subrip` or (commonly accepted) `text/plain`. `text/vtt` is correct per spec.

**Fix:**

```python
_MEDIA_TYPES = {
    "json": "application/json",
    "srt": "application/x-subrip",
    "vtt": "text/vtt",
}
media = _MEDIA_TYPES[format]
```

---

### m-4 · `result_writer.py:14-17` — Millis overflow guard is a smell hiding a floating-point issue

```python
millis = round((seconds - int(seconds)) * 1000)
if millis == 1000:     # floating-point rounding artefact
    secs += 1
    millis = 0
```

The guard is correct but the comment is absent. An intention-revealing comment clarifies this is not a logic bug:

```python
# round() can produce 1000 when seconds is e.g. 1.9995 — carry into seconds
if millis == 1000:
    secs += 1
    millis = 0
```

---

### m-5 · `gateway/rest_models.py:12` — Hard-coded path constant at module level without explanation

```python
VERSION_FILE = Path("/opt/vibevoice/current_model/version.json")
```

This path is deployment-specific and non-configurable. An environment variable fallback would reduce coupling to a specific container layout.

**Fix (optional, low priority):**

```python
import os
VERSION_FILE = Path(os.environ.get(
    "VIBEVOICE_VERSION_FILE", "/opt/vibevoice/current_model/version.json"
))
```

---

### m-6 · `hotword_merger.py:8` — `parse_csv` is a general utility living in a domain-specific module

`parse_csv` is imported by `transcribe.py` and used in at least three contexts (hotword parsing, group ID parsing). Its home in `hotword_merger.py` is an implementation detail that leaks to callers.

**Fix (low urgency):** move `parse_csv` to `shared/validation.py` or a `shared/utils.py`. Keep a re-export in `hotword_merger.py` for backward compatibility with tests.

---

### m-7 · `audio_normalizer.py` — `is_video_file` accepts `str` filename but callers pass `Path` objects

```python
def is_video_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXT_SET
```

In `tasks/transcribe.py` the call is `is_video_file` (not called directly with a Path — kind is derived from `check_filename_ext` instead). However the function signature says `str` while `Path(filename)` works transparently with both. Aligning the signature prevents confusion:

```python
def is_video_file(filename: str | Path) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTS
```

---

## Summary Table

| Severity | Count | Categories |
|---|---|---|
| Critical | 8 | async/sync mismatch (C-1, C-2), encapsulation (C-3), inline imports (C-4, C-5), SRP/function size (C-6), N+1 query (C-7), swallowed exceptions (C-8) |
| Important | 9 | DRY `_now()` (I-1), alias (I-2), dead branch (I-3, I-8), deferred imports (I-4), DRY construction (I-5), missing types (I-6), magic constant (I-7), magic string (I-9) |
| Minor | 7 | Clarity/naming (m-1, m-4, m-6), MIME type (m-3), atomicity (m-2), hard-coded path (m-5), type signature (m-7) |

---

## Prioritised Fix Order

1. **C-1 + C-2** (async/sync Redis) — can cause real production latency spikes under concurrent load
2. **C-3** (private method access) — quick one-liner fix, eliminates encapsulation breach
3. **C-4 + C-5 + I-4** (all inline imports) — mechanical, safe, improves dep graph clarity
4. **C-7** (N+1 hotword query) — one-line fix, reduces DB calls from N to 1
5. **C-8 + I-8** (swallowed exceptions / misleading comment) — zero-risk, improves observability
6. **I-1** (duplicate `_now()`) — small refactor, good DRY hygiene
7. **C-6** (ws_transcribe function decomposition) — largest effort, highest long-term payoff; do separately to avoid merge conflicts
