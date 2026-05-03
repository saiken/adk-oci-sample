from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Make `agents/*` importable as top-level packages (common/orchestrator/etc).
sys.path.insert(0, str(Path(__file__).parent / "agents"))

def _env_flag(name: str) -> bool:
  value = os.getenv(name, "").strip().lower()
  return value in ("1", "true", "yes", "on")


def _maybe_load_dotenv() -> None:
  # In OCI (prod), prefer injecting environment variables via the runtime
  # (e.g., deployment config / secrets). Enable dotenv only for local/dev.
  env = os.getenv("ENV", "").strip().lower()
  if env in ("local", "dev") or _env_flag("LOAD_DOTENV"):
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

from orchestrator.agent import root_agent


APP_NAME = os.getenv("ADK_APP_NAME", "adk-oci-sample")
USER_ID = os.getenv("ADK_USER_ID", "user")
SESSION_ID = os.getenv("ADK_SESSION_ID", "default")

session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)

_session_lock = asyncio.Lock()


async def _ensure_session() -> None:
  async with _session_lock:
    # Be conservative: always attempt to create first. If it already exists,
    # fall back to get_session. This avoids "session not found" races/edge-cases
    # across ADK versions.
    try:
      await session_service.create_session(
          app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
      )
      return
    except Exception:
      await session_service.get_session(
          app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
      )


class MessageRequest(BaseModel):
  message: str


class MessageResponse(BaseModel):
  response: str


app = FastAPI(title="ADK Agent API", version="0.1.0")


@app.post("/message", response_model=MessageResponse)
async def post_message(payload: MessageRequest) -> MessageResponse:
  request_id = uuid.uuid4().hex[:12]
  message = (payload.message or "").strip()
  if not message:
    raise HTTPException(status_code=400, detail="`message` is required.")

  logger.info("[%s] request message=%r", request_id, message)

  await _ensure_session()

  user_content = types.Content(role="user", parts=[types.Part(text=message)])

  full_stream_text = ""
  final_text: Optional[str] = None
  last_text: str = ""
  try:
    async for event in runner.run_async(
        user_id=USER_ID, session_id=SESSION_ID, new_message=user_content
    ):
      author = getattr(event, "author", "unknown")
      partial = bool(getattr(event, "partial", False))

      # Best-effort text extraction for logs/response.
      try:
        text = event.stringify_content() or ""
      except Exception:
        text = ""
      if not text:
        try:
          content = getattr(event, "content", None)
          parts = getattr(content, "parts", None) if content is not None else None
          if parts:
            text = "".join((getattr(p, "text", "") or "") for p in parts).strip()
        except Exception:
          text = ""
      if text:
        last_text = text

      # Log function calls / responses if present (helps trace per-agent behavior).
      try:
        fn_calls = event.get_function_calls()
      except Exception:
        fn_calls = []
      try:
        fn_resps = event.get_function_responses()
      except Exception:
        fn_resps = []

      logger.info(
          "[%s] event author=%s partial=%s final=%s text=%r calls=%d responses=%d",
          request_id,
          author,
          partial,
          bool(getattr(event, "is_final_response", lambda: False)()),
          (text[:500] + "…") if len(text) > 500 else text,
          len(fn_calls) if fn_calls else 0,
          len(fn_resps) if fn_resps else 0,
      )

      # If streaming is enabled by the underlying model adapter, accumulate chunks.
      try:
        if partial:
          if text:
            full_stream_text += text
      except Exception:
        pass

      try:
        is_final = event.is_final_response()
      except Exception:
        is_final = False

      if is_final:
        final_text = (
            full_stream_text + ("" if partial else text)
        ).strip() or (text or "").strip()
        full_stream_text = ""
  except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Agent execution failed: {exc}") from exc

  if not final_text:
    final_text = full_stream_text.strip() or last_text.strip() or ""
  logger.info("[%s] response=%r", request_id, final_text[:1000])
  return MessageResponse(response=final_text)


def main() -> None:
  host = os.getenv("HOST", "127.0.0.1")
  port = int(os.getenv("PORT", "8000"))
  uvicorn.run("main:app", host=host, port=port, reload=os.getenv("RELOAD") == "1")


if __name__ == "__main__":
    main()
