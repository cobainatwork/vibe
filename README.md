# VibeVoice Client

V-Client deployment package. See `docs/superpowers/specs/2026-05-21-vibevoice-impl-design.md`.

## E2E Tests

After `docker compose up -d` and `scripts/wait_for_ready.sh`:

    E2E_BASE_URL=http://localhost:8000 \
    E2E_API_KEY=$(grep key config/api_keys.yaml | head -1 | awk -F: '{print $2}' | tr -d ' ') \
    uv run pytest tests/e2e/ -m e2e -v
