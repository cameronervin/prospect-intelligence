"""Declarative tool registry and assignment helpers."""

from .registry import TOOL_REGISTRY, ToolSpec, tools_for_agent

__all__ = ["TOOL_REGISTRY", "ToolSpec", "tools_for_agent"]
