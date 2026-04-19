"""
SpielBot FastAPI service — wraps SpielBotSession for the React frontend.

Run from repo root:
  uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bgg_config import GAMES  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from index import ChunkIndex  # noqa: E402
from orchestrator import SpielBotSession  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from retrieve import sources_for_api  # noqa: E402

MAX_IMAGE_BYTES = 10 * 1024 * 1024

_shared_index: ChunkIndex | None = None
sessions: dict[str, SpielBotSession] = {}


def _get_cors_origins() -> list[str]:
    raw = os.environ.get(
        "SPIELBOT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_shared_index() -> ChunkIndex:
    global _shared_index
    if _shared_index is None:
        _shared_index = ChunkIndex(ROOT)
    return _shared_index


def new_bot_session() -> SpielBotSession:
    return SpielBotSession(index=get_shared_index(), eager_load=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_shared_index()
    yield


app = FastAPI(title="SpielBot API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionBody(BaseModel):
    game: str


class ChatBody(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    image_base64: str | None = None
    mime_type: str | None = None


def _decode_image_b64(data: str | None) -> bytes | None:
    if not data or not data.strip():
        return None
    s = data.strip()
    if s.startswith("data:"):
        comma = s.find(",")
        if comma != -1:
            s = s[comma + 1 :]
    s = re.sub(r"\s+", "", s)
    try:
        raw = base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)",
        )
    return raw


def _session_or_404(session_id: str) -> SpielBotSession:
    sess = sessions.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    return sess


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "index_loaded": _shared_index is not None,
    }


@app.post("/v1/sessions")
def create_session(body: CreateSessionBody) -> dict[str, str]:
    if body.game not in GAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown game. Valid: {', '.join(GAMES)}",
        )
    sid = str(uuid.uuid4())
    sess = new_bot_session()
    sess.select_game(body.game)
    sessions[sid] = sess
    return {"session_id": sid}


@app.delete("/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, bool]:
    sessions.pop(session_id, None)
    return {"ok": True}


@app.post("/v1/chat")
def chat(body: ChatBody) -> dict[str, Any]:
    sess = _session_or_404(body.session_id)
    if not sess.has_game:
        raise HTTPException(status_code=400, detail="Session has no game selected")

    img = _decode_image_b64(body.image_base64)
    t0 = time.perf_counter()
    result = sess.ask(body.message.strip(), image=img)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    sub_q: list[str] = []
    if result.reasoning and result.reasoning.sub_questions:
        sub_q = list(result.reasoning.sub_questions)

    src_list = sources_for_api(result.sources) if result.sources else []

    return {
        "answer": result.answer,
        "sources": src_list,
        "sub_questions": sub_q,
        "error": result.error,
        "latency_ms": latency_ms,
    }


def _sse_token(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/stream")
def chat_stream(body: ChatBody):
    sess = _session_or_404(body.session_id)
    if not sess.has_game:
        raise HTTPException(status_code=400, detail="Session has no game selected")

    img = _decode_image_b64(body.image_base64)

    def event_iter():
        t0 = time.perf_counter()
        try:
            sources, streamer = sess.ask_stream(body.message.strip(), image=img)
        except Exception as ex:
            yield _sse_token({"type": "error", "message": str(ex)})
            return

        gen_response = None
        it = iter(streamer)
        try:
            while True:
                chunk = next(it)
                yield _sse_token({"type": "token", "text": chunk})
        except StopIteration as e:
            gen_response = e.value

        latency_ms = int((time.perf_counter() - t0) * 1000)
        if gen_response is None:
            yield _sse_token(
                {
                    "type": "done",
                    "answer": "",
                    "sources": [],
                    "sub_questions": [],
                    "error": "No response from generator",
                    "latency_ms": latency_ms,
                }
            )
            return

        answer = (gen_response.answer or "").strip()
        err = gen_response.error

        if not err and sources:
            sess.commit_to_history(body.message.strip(), answer)

        lr = sess.last_reasoning
        sub_q = list(lr.sub_questions) if lr and lr.sub_questions else []

        yield _sse_token(
            {
                "type": "done",
                "answer": answer,
                "sources": sources_for_api(sources) if sources else [],
                "sub_questions": sub_q,
                "error": err,
                "latency_ms": latency_ms,
            }
        )

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
