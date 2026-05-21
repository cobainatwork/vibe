#!/usr/bin/env bash
set -euo pipefail

PORT="${GATEWAY_PORT:-8000}"
KEY_FILE="${KEY_FILE:-config/api_keys.yaml}"
KEY=$(grep -E '^\s*-?\s*key:' "$KEY_FILE" | head -1 | awk -F':' '{print $2}' | tr -d ' "')

echo "1. /v1/health"
curl -s -H "X-API-Key: $KEY" "http://localhost:${PORT}/v1/health" | tee /dev/stderr
echo ""

echo "2. /v1/models/current"
curl -s -H "X-API-Key: $KEY" "http://localhost:${PORT}/v1/models/current" | tee /dev/stderr
echo ""

# WS test requires Python (more reliable than bash WS)
echo "3. WS transcribe (3-second sample)"
python3 - <<PYEOF
import asyncio, base64, json, subprocess, tempfile
import websockets

async def main():
    # Generate 3s test tone
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         tmp.name], capture_output=True, check=True
    )
    audio = open(tmp.name, "rb").read()

    uri = "ws://localhost:${PORT}/v1/transcribe"
    async with websockets.connect(
        uri, additional_headers={"X-API-Key": "$KEY"}
    ) as ws:
        await ws.send(json.dumps({"type": "start", "filename": "tone.wav"}))
        ready = json.loads(await ws.recv())
        print("ready:", ready)
        await ws.send(audio)
        await ws.send(json.dumps({"type": "eof"}))
        while True:
            msg = json.loads(await ws.recv())
            print(msg)
            if msg.get("type") in ("done", "error"):
                break

asyncio.run(main())
PYEOF
