"""Session management tools."""

from __future__ import annotations

from typing import Any, Dict, List

from .contracts import EXAMPLE_EMPTY_SPATIAL_STATE, create_session_output_schema
from .metadata import tool_contract


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "create_session",
        "title": "Create Session",
        **tool_contract(
            summary="Create or recover a CADAgent modeling session.",
            when_to_use="This is the required first call before any geometry tool, or when you must recover a live session for the current conversation.",
            when_not_to_use="Do not use this to inspect geometry, edit a body, or export artifacts.",
            authoritative_result="session_id, status, expires_at, and spatial_state are authoritative for whether modeling can continue and whether geometry already exists.",
            follow_up="Usually call write_spec to create or update geometry, then export when the model is ready.",
            failure_handling="If the backend cannot recover the requested session, surface that failure and create a fresh session instead of guessing prior state.",
            input_field_semantics={
                "client_session_hint": "Optional host or conversation identifier used to recover a matching live CAD session.",
                "metadata": "Optional client metadata for traceability. Do not send secrets.",
            },
            output_field_semantics={
                "session_id": "Authoritative identifier required by every later tool call.",
                "status": "Session lifecycle state returned by the backend.",
                "expires_at": "Expiry timestamp that determines whether reuse is still valid.",
                "spatial_state": "Ground-truth current geometry state; mode=empty means no body exists yet.",
            },
            follow_up_tools=["write_spec", "export"],
            common_failures=[
                {"code": "SESSION_EXPIRED", "recovery": "Request or create a fresh session before continuing."},
                {"code": "INTERNAL_ERROR", "recovery": "Surface the backend failure instead of assuming a usable session exists."},
            ],
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "client_session_hint": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "additionalProperties": False,
        },
        "outputSchema": create_session_output_schema(),
        "examples": [
            {
                "structuredContent": {
                    "session_id": "sess_123",
                    "expires_at": "2026-03-17T12:00:00+00:00",
                    "status": "active",
                    "summary": "Session ready for spec-only MCP authoring.",
                    "spatial_state": EXAMPLE_EMPTY_SPATIAL_STATE,
                }
            }
        ],
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    }
]


async def create_session(arguments: Dict[str, Any], backend_client: Any) -> Dict[str, Any]:
    return await backend_client.create_session(arguments)


HANDLERS = {"create_session": create_session}
