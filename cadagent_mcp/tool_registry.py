"""Tool registry for CADAgent MCP server."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from .backend_client import BackendClient
from .tools import authoring, export, session


ToolHandler = Callable[[Dict[str, Any], BackendClient], Awaitable[Dict[str, Any]]]

TOOL_DEFINITIONS: List[Dict[str, Any]] = session.TOOLS + authoring.TOOLS + export.TOOLS

TOOL_HANDLERS: Dict[str, ToolHandler] = {}
TOOL_HANDLERS.update(session.HANDLERS)
TOOL_HANDLERS.update(authoring.HANDLERS)
TOOL_HANDLERS.update(export.HANDLERS)


async def call_tool(name: str, arguments: Dict[str, Any], backend_client: BackendClient) -> Dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise KeyError(f"Unknown tool: {name}")
    return await handler(arguments, backend_client)
