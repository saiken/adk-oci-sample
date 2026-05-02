from __future__ import annotations

import os

from google.adk.models.base_llm import BaseLlm
from google.genai import types


def get_default_model() -> str | BaseLlm:
  """Returns the model configuration used by all agents.

  - ADK_MODEL=openai: returns a LiteLLM model string (default: openai/gpt-5.2)
    via ADK_OPENAI_MODEL.
  - ADK_MODEL=oci: returns an OCI Generative AI adapter instance.
  """
  adk_model = os.getenv("ADK_MODEL", "openai").strip().lower()
  if adk_model == "oci":
    from oci_expert.oci_llm import OciGenerativeAiLlm

    return OciGenerativeAiLlm.from_env()

  return os.getenv("ADK_OPENAI_MODEL", "openai/gpt-5.2").strip()


def get_generate_content_config() -> types.GenerateContentConfig:
  """Returns a shared GenerateContentConfig for agents."""
  max_output_tokens = int(os.getenv("ADK_MAX_OUTPUT_TOKENS", "1024"))
  temperature = float(os.getenv("ADK_TEMPERATURE", "0.0"))
  top_p = float(os.getenv("ADK_TOP_P", "0.75"))
  return types.GenerateContentConfig(
      max_output_tokens=max_output_tokens,
      temperature=temperature,
      top_p=top_p,
  )
