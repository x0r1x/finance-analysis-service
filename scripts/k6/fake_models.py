"""Поддельные серверы моделей для сценария S5 (§4.13.9): медленный или падающий embed/rerank/CLM.

    FAKE_MODE=slow FAKE_DELAY_SEC=5 uvicorn deploy.k6.fake_models:app --port 8901

FAKE_MODE: ok | slow | fail | flaky (каждый второй запрос — 503).
FAS указывает на сервер через EMBED_BASE_URL, RERANK_BASE_URL, CLM_BASE_URL=http://…/v1/systemone.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
_counter = itertools.count()
DIM = 32


def _mode() -> str:
    return os.environ.get("FAKE_MODE", "ok")


async def _gate():
    mode = _mode()
    if mode == "slow":
        await asyncio.sleep(float(os.environ.get("FAKE_DELAY_SEC", "5")))
    if mode == "fail" or (mode == "flaky" and next(_counter) % 2 == 0):
        return JSONResponse({"error": "fake failure"}, status_code=503)
    return None


def _vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [byte / 255 for byte in digest[:DIM]]


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    if (failed := await _gate()) is not None:
        return failed
    body = await request.json()
    return {"data": [{"index": index, "embedding": _vector(text)} for index, text in enumerate(body["input"])]}


@app.post("/v1/rerank")
async def rerank(request: Request):
    if (failed := await _gate()) is not None:
        return failed
    body = await request.json()
    scores = [{"index": index, "relevance_score": 1 / (index + 1)} for index, _doc in enumerate(body["documents"])]
    return {"results": scores[: body.get("top_n") or len(scores)]}


@app.post("/v1/systemone")
async def systemone(request: Request):
    if (failed := await _gate()) is not None:
        return failed
    body = await request.json()
    out = {}
    for name, question in body["questions"].items():
        keys = list(question["criteria"])
        out[name] = {"choice": keys[0], "probabilities": {key: (0.7 if i == 0 else 0.3 / max(len(keys) - 1, 1)) for i, key in enumerate(keys)}}
    return {"questions": out}
