"""Backward-compatible wrapper.

Prefer running:
- `adk run agents/orchestrator`
- `adk web agents`
"""

import importlib

# ADK loads each agent directory as a top-level module (e.g. `orchestrator`),
# so we import the sibling module by its top-level name.
agent = importlib.import_module("orchestrator.agent")  # noqa: F401
