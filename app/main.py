"""
main.py — CourtLink2 Agent FastAPI server.

Endpoints:
    POST /chat          — send a message, get an agent reply
    DELETE /chat/{id}   — clear conversation history for a session
    GET  /health        — health check (DB + API connectivity)
    GET  /              — serve the chat UI (static/index.html)

Run:
    cd courtlink2-agent
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import uuid
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env from the courtlink2-agent directory
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

from .agent import run_agent  # noqa: E402 — must load after dotenv

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CourtLink2 Agent",
    description="AI assistant for the CourtLink2 video visitation system.",
    version="1.0.0",
)

# Serve the static chat UI
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── Request / Response models ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""  # if empty, a new session ID is generated


class ChatResponse(BaseModel):
    reply: str
    session_id: str


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the chat web UI."""
    index = _STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Chat UI not found.")
    return FileResponse(str(index))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the CourtLink2 agent and receive a reply.

    - If `session_id` is empty, a new session is created and its ID is returned.
    - Pass the same `session_id` in follow-up messages to maintain conversation context.
    """
    session_id = request.session_id.strip() or str(uuid.uuid4())

    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    try:
        reply = run_agent(session_id, request.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return ChatResponse(reply=reply, session_id=session_id)


@app.delete("/chat/{session_id}", status_code=204)
async def clear_session(session_id: str) -> None:
    """
    Clear the conversation history for the given session.
    The session ID can be reused afterwards with a fresh context.
    """
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chat_sessions WHERE session_id = %s",
                (session_id,),
            )
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc


@app.get("/health")
async def health() -> JSONResponse:
    """
    Health check. Verifies PostgreSQL connectivity.
    Returns 200 if healthy, 503 if the database is unreachable.
    """
    checks: dict = {}

    # PostgreSQL
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            doc_count = cur.fetchone()[0]
        conn.close()
        checks["postgres"] = {"status": "ok", "document_chunks": doc_count}
    except Exception as e:
        checks["postgres"] = {"status": "error", "detail": str(e)}

    healthy = all(v.get("status") == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ok" if healthy else "degraded", "checks": checks},
        status_code=200 if healthy else 503,
    )
