#!/usr/bin/env bash
set -euo pipefail

PORT="${GATEWAY_PORT:-8000}"
MAX_WAIT="${MAX_WAIT:-600}"
KEY_FILE="${KEY_FILE:-config/api_keys.yaml}"

# Extract first key from yaml (very lightweight; assumes standard format)
KEY=$(grep -E '^\s*-?\s*key:' "$KEY_FILE" | head -1 | awk -F':' '{print $2}' | tr -d ' "')

if [ -z "$KEY" ]; then
    echo "No API key found in $KEY_FILE"
    exit 1
fi

echo "Polling http://localhost:${PORT}/v1/health for up to ${MAX_WAIT}s ..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    resp=$(curl -s -o /tmp/health.json -w "%{http_code}" -H "X-API-Key: $KEY" \
           "http://localhost:${PORT}/v1/health" 2>/dev/null || echo "000")
    if [ "$resp" = "200" ]; then
        if grep -q '"vllm_ready": *true' /tmp/health.json; then
            echo "✅ Ready (vllm_ready=true)"
            cat /tmp/health.json
            exit 0
        fi
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    echo "  ... still waiting (${elapsed}s, last status: $resp)"
done

echo "❌ Timed out waiting for ready."
exit 1
