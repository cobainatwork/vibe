"""Fake vLLM server for tests.

Mounts as a FastAPI app you can start with uvicorn or test with httpx.
Returns a pre-canned SSE stream based on a query param.
"""
import json

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

CANNED = {
    "happy": [
        '[{"Start time":"0.00","End time":"2.50","Speaker ID":"0","Content":"你好"}',
        ',{"Start time":"2.50","End time":"5.20","Speaker ID":"1","Content":"嗨"}]',
    ],
    "repetition": ["你好" * 30],  # will trigger detector
    "error_5xx": None,  # special, see below
}


def _to_sse_lines(chunks: list[str]):
    for ch in chunks:
        yield f"data: {json.dumps({'choices':[{'delta':{'content': ch}}]})}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def completions(req: Request):
    body = await req.json()
    # Extract scenario from prompt text hint (we encode scenario in user text for tests)
    scenario = req.query_params.get("scenario", "happy")
    if scenario == "error_5xx":
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="fake error")
    chunks = CANNED.get(scenario, CANNED["happy"])
    return StreamingResponse(
        _to_sse_lines(chunks),
        media_type="text/event-stream",
    )


@app.get("/v1/models")
async def models():
    return {"data": [{"id": "vibevoice"}]}
