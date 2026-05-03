from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Optional

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr


class OciGenerativeAiLlm(BaseLlm):
  """OCI Generative AI (Inference) LLM adapter for Google ADK.

  This adapter is shared across agents. Agent-specific prompting / tooling
  should live in each agent module, not here.
  """

  _client: object = PrivateAttr(default=None)
  _compartment_id: str = PrivateAttr(default="")
  _api_format: str = PrivateAttr(default="generic")  # generic|cohere

  @classmethod
  def from_env(cls, *, model_id: Optional[str] = None) -> "OciGenerativeAiLlm":
    compartment_id = os.getenv("OCI_COMPARTMENT_ID", "").strip()
    if not compartment_id:
      raise ValueError("OCI_COMPARTMENT_ID is required for OCI Generative AI.")

    api_format = os.getenv("OCI_CHAT_API_FORMAT", "generic").strip().lower()
    if api_format not in ("generic", "cohere"):
      raise ValueError("OCI_CHAT_API_FORMAT must be one of: generic, cohere")

    resolved_model_id = (model_id or os.getenv("OCI_MODEL_ID", "")).strip()
    if not resolved_model_id:
      raise ValueError("OCI_MODEL_ID (or model_id) is required for OCI Generative AI.")

    instance = cls(model=resolved_model_id)
    instance._compartment_id = compartment_id
    instance._api_format = api_format
    instance._client = _create_oci_inference_client()
    return instance

  async def generate_content_async(
      self, llm_request: LlmRequest, stream: bool = False
  ) -> AsyncGenerator[LlmResponse, None]:
    if stream:
      raise NotImplementedError("Streaming is not implemented for OCI adapter.")
    if self._client is None:
      raise RuntimeError("OCI client is not initialized.")

    self._maybe_append_user_content(llm_request)
    system_instruction = getattr(llm_request.config, "system_instruction", None)

    chat_details = _build_chat_details(
        compartment_id=self._compartment_id,
        model_id=self.model,
        api_format=self._api_format,
        system_instruction=system_instruction if isinstance(system_instruction, str) else None,
        contents=llm_request.contents,
        temperature=_safe_float(getattr(llm_request.config, "temperature", None)),
        max_tokens=_safe_int(getattr(llm_request.config, "max_output_tokens", None)),
        top_p=_safe_float(getattr(llm_request.config, "top_p", None)),
    )

    response = await asyncio.to_thread(self._client.chat, chat_details)
    chat_result = getattr(response, "data", None)
    output_text = _extract_oci_chat_text(chat_result)
    yield LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=output_text)]),
        model_version=getattr(chat_result, "model_version", None),
    )


def _create_oci_inference_client():
  try:
    import oci  # type: ignore
    from oci.generative_ai_inference import GenerativeAiInferenceClient  # type: ignore
  except Exception as exc:  # pragma: no cover
    raise ImportError(
        "OCI Generative AI requires the OCI Python SDK. Install it with `uv sync`."
    ) from exc

  auth = os.getenv("OCI_AUTH", "api_key").strip().lower()
  region = os.getenv("OCI_REGION", "").strip() or None

  if auth == "resource_principal":
    signer = oci.auth.signers.get_resource_principals_signer()
    config = {"region": region} if region else {}
    return GenerativeAiInferenceClient(config=config, signer=signer)

  config_file = os.getenv("OCI_CONFIG_FILE", "~/.oci/config")
  profile = os.getenv("OCI_PROFILE", "DEFAULT")
  config = oci.config.from_file(
      file_location=os.path.expanduser(config_file),
      profile_name=profile,
  )
  if region:
    config["region"] = region
  return GenerativeAiInferenceClient(config=config)


def _build_chat_details(
    *,
    compartment_id: str,
    model_id: str,
    api_format: str,
    system_instruction: Optional[str],
    contents: list[types.Content],
    temperature: Optional[float],
    max_tokens: Optional[int],
    top_p: Optional[float],
):
  from oci.generative_ai_inference import models  # type: ignore

  serving = models.OnDemandServingMode(model_id=model_id)

  if api_format == "generic":
    oci_messages: list[object] = []
    if system_instruction and system_instruction.strip():
      oci_messages.append(_oci_message("SYSTEM", system_instruction))
    for content in contents:
      text = _extract_text(content)
      if not text:
        continue
      role = (content.role or "").lower()
      if role == "user":
        oci_messages.append(_oci_message("USER", text))
      else:
        oci_messages.append(_oci_message("ASSISTANT", text))

    kwargs = {
        "api_format": models.GenericChatRequest.API_FORMAT_GENERIC,
        "messages": oci_messages,
    }
    if temperature is not None:
      kwargs["temperature"] = temperature
    if max_tokens is not None:
      kwargs["max_tokens"] = max_tokens
    if top_p is not None:
      kwargs["top_p"] = top_p
    chat_request = models.GenericChatRequest(**kwargs)
  else:
    latest_user_message = _extract_text(contents[-1]) if contents else ""
    if not latest_user_message:
      latest_user_message = "Continue."

    chat_history: list[object] = []
    if system_instruction and system_instruction.strip():
      chat_history.append(
          models.CohereSystemMessage(role="SYSTEM", message=system_instruction)
      )
    for content in contents[:-1]:
      text = _extract_text(content)
      if not text:
        continue
      role = (content.role or "").lower()
      if role == "user":
        chat_history.append(models.CohereUserMessage(role="USER", message=text))
      else:
        chat_history.append(models.CohereChatBotMessage(role="CHATBOT", message=text))

    kwargs = {
        "api_format": models.CohereChatRequest.API_FORMAT_COHERE,
        "message": latest_user_message,
        "chat_history": chat_history,
    }
    if temperature is not None:
      kwargs["temperature"] = temperature
    if max_tokens is not None:
      kwargs["max_tokens"] = max_tokens
    if top_p is not None:
      kwargs["top_p"] = top_p
    chat_request = models.CohereChatRequest(**kwargs)

  return models.ChatDetails(
      compartment_id=compartment_id,
      serving_mode=serving,
      chat_request=chat_request,
  )


def _oci_message(role: str, text: str) -> object:
  from oci.generative_ai_inference import models  # type: ignore

  return models.Message(role=role, content=[models.TextContent(text=text)])


def _extract_text(content: types.Content) -> str:
  if not content.parts:
    return ""
  return "".join(part.text or "" for part in content.parts).strip()


def _extract_oci_chat_text(chat_result: object) -> str:
  if chat_result is None:
    return ""
  chat_response = getattr(chat_result, "chat_response", None)
  text = getattr(chat_response, "text", None)
  if isinstance(text, str) and text.strip():
    return text
  choices = getattr(chat_response, "choices", None)
  if not choices:
    return ""
  first = choices[0]
  message = getattr(first, "message", None)
  content = getattr(message, "content", None) or []
  parts: list[str] = []
  for item in content:
    t = getattr(item, "text", None)
    if isinstance(t, str):
      parts.append(t)
  return "".join(parts).strip()


def _safe_float(value) -> Optional[float]:
  try:
    return None if value is None else float(value)
  except (TypeError, ValueError):
    return None


def _safe_int(value) -> Optional[int]:
  try:
    return None if value is None else int(value)
  except (TypeError, ValueError):
    return None

