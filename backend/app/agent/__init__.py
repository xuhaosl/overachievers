"""Agent 子系统。"""
from .prompts import AGENT_SYSTEM_PROMPT, build_system_prompt
from .runtime import agent_event_stream, list_pending
from .tools import (
    READ_TOOLS,
    TOOL_NAMES,
    TOOL_SPECS,
    WRITE_TOOLS,
    ToolContext,
    ToolError,
    confirm_pending,
    execute_tool,
    tool_specs_for,
)

__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "build_system_prompt",
    "agent_event_stream",
    "list_pending",
    "READ_TOOLS",
    "TOOL_NAMES",
    "TOOL_SPECS",
    "WRITE_TOOLS",
    "ToolContext",
    "ToolError",
    "confirm_pending",
    "execute_tool",
    "tool_specs_for",
]
