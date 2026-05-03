from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel


def _maybe_load_dotenv() -> None:
  # In OCI (prod), prefer injecting environment variables via the runtime
  # (e.g., deployment config / secrets). Enable dotenv only for local/dev.
  env = os.getenv("ENV", "").strip().lower()
  if env == "local":
    try:
      from dotenv import load_dotenv  # type: ignore
    except Exception:
      return
    load_dotenv(Path(__file__).parent / ".env")


_maybe_load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("adk_api")

from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.orchestrator.agent import root_agent

APP_NAME = os.getenv("ADK_APP_NAME", "adk-oci-sample").strip() or "adk-oci-sample"

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)

_session_locks: dict[tuple[str, str], asyncio.Lock] = {}


class MessageRequest(BaseModel):
  message: str


class MessageResponse(BaseModel):
  session_id: str
  response: str


app = FastAPI(title="ADK Agent API", version="0.1.0")


@app.post("/message", response_model=MessageResponse)
async def post_message(payload: MessageRequest, request: Request) -> MessageResponse:
  request_id = uuid.uuid4().hex[:12]
  message = (payload.message or "").strip()
  if not message:
    raise HTTPException(status_code=400, detail="`message` is required.")

  user_id, session_id = _get_user_and_session_id(request)

  logger.info(
      "[%s] request user_id=%s session_id=%s message=%r",
      request_id,
      user_id,
      session_id,
      message,
  )

  await _ensure_session(user_id=user_id, session_id=session_id)

  user_content = _build_user_content(message)
  response_text = ""
  try:
    response_text = await _run_agent_and_collect_text(
        user_id=user_id,
        session_id=session_id,
        user_content=user_content,
        request_id=request_id,
    )
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

  logger.info("[%s] response=%r", request_id, response_text[:1000])
  return MessageResponse(session_id=session_id, response=response_text)


def main() -> None:
  host = os.getenv("HOST", "127.0.0.1")
  port = int(os.getenv("PORT", "8000"))
  uvicorn.run("main:app", host=host, port=port, reload=os.getenv("RELOAD") == "1")


if __name__ == "__main__":
    main()


def _get_session_lock(user_id: str, session_id: str) -> asyncio.Lock:
  key = (user_id, session_id)
  lock = _session_locks.get(key)
  if lock is None:
    lock = asyncio.Lock()
    _session_locks[key] = lock
  return lock


async def _ensure_session(*, user_id: str, session_id: str) -> None:
  lock = _get_session_lock(user_id, session_id)
  async with lock:
    # Prefer a non-exceptional "check then create" flow. Depending on the ADK
    # version, get_session may return None or raise when missing; handle both.
    session = None
    try:
      session = await session_service.get_session(
          app_name=APP_NAME, user_id=user_id, session_id=session_id
      )
    except Exception:
      session = None

    if session is None:
      await session_service.create_session(
          app_name=APP_NAME, user_id=user_id, session_id=session_id
      )


def _get_user_and_session_id(request: Request) -> Tuple[str, str]:
  # Session isolation without login:
  # - user_id and session_id are the same value.
  # - If the client supplies X-Session-Id, we keep conversation state.
  # - Otherwise, we generate a UUID so sessions never collide.
  session_id = (request.headers.get("x-session-id") or "").strip()
  if not session_id:
    session_id = uuid.uuid4().hex
  user_id = session_id
  return user_id, session_id


def _build_user_content(message: str) -> types.Content:
  return types.Content(role="user", parts=[types.Part(text=message)])


def _extract_event_text(event: object) -> str:
  try:
    text = getattr(event, "stringify_content")() or ""
  except Exception:
    text = ""
  if text:
    return text

  try:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if parts:
      return "".join((getattr(p, "text", "") or "") for p in parts).strip()
  except Exception:
    pass
  return ""


def _safe_is_final(event: object) -> bool:
  try:
    return bool(getattr(event, "is_final_response")())
  except Exception:
    return False


def _safe_function_calls_count(event: object) -> tuple[int, int]:
  try:
    calls = getattr(event, "get_function_calls")()
  except Exception:
    calls = []
  try:
    responses = getattr(event, "get_function_responses")()
  except Exception:
    responses = []
  return (len(calls) if calls else 0, len(responses) if responses else 0)


def _log_event(*, request_id: str, event: object, text: str) -> None:
  author = getattr(event, "author", "unknown")
  partial = bool(getattr(event, "partial", False))
  is_final = _safe_is_final(event)
  calls_count, responses_count = _safe_function_calls_count(event)

  logger.info(
      "[%s] event author=%s partial=%s final=%s text=%r calls=%d responses=%d",
      request_id,
      author,
      partial,
      is_final,
      (text[:500] + "…") if len(text) > 500 else text,
      calls_count,
      responses_count,
  )


async def _run_agent_and_collect_text(
    *, user_id: str, session_id: str, user_content: types.Content, request_id: str
) -> str:
  full_stream_text = ""
  final_text: Optional[str] = None
  last_text = ""

  async for event in runner.run_async(
      user_id=user_id, session_id=session_id, new_message=user_content
  ):
    partial = bool(getattr(event, "partial", False))
    text = _extract_event_text(event)
    if text:
      last_text = text

    _log_event(request_id=request_id, event=event, text=text)

    if partial and text:
      full_stream_text += text

    if _safe_is_final(event):
      final_text = (full_stream_text + ("" if partial else text)).strip() or text.strip()
      full_stream_text = ""

  return final_text or full_stream_text.strip() or last_text.strip() or ""
