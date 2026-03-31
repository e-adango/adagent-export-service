"""Export tool contract."""

from __future__ import annotations

from typing import Any, Dict, List

from .contracts import export_output_schema
from .metadata import tool_contract


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "export",
        "title": "Export Model",
        **tool_contract(
            summary="Export the current model to STEP, STL, or GLB and return cadagent.co download-page links.",
            when_to_use="Use when the modeled result is ready for delivery, download, or handoff to another CAD or fabrication workflow.",
            when_not_to_use="Do not claim export success before this tool returns resource_link and download_url. It is the authoritative export step.",
            authoritative_result="format, resource_link, download_url, expires_at, content, and spatial_state are authoritative for export availability and current model snapshot.",
            follow_up="Present the export link, download URL, what changed, and any validation summary grounded in the returned spatial_state.",
            failure_handling="If export generation fails or a format is unsupported, surface the backend error clearly and do not fabricate links.",
            input_field_semantics={
                "session_id": "Active CADAgent modeling session.",
                "format": "Requested export format: step, stl, or glb.",
            },
            output_field_semantics={
                "resource_link": "cadagent.co download-page link suitable for user-facing export access.",
                "download_url": "Direct artifact download URL returned by the backend.",
                "expires_at": "Export expiration timestamp.",
                "content": "User-facing content blocks that can be echoed in the final response.",
                "spatial_state": "Ground-truth geometry snapshot associated with the exported model.",
            },
            follow_up_tools=[],
            common_failures=[
                {"code": "UNSUPPORTED_EXPORT_FORMAT", "recovery": "Retry with step, stl, or glb."},
                {"code": "BACKEND_EXECUTION_FAILED", "recovery": "Surface the export failure; do not claim a file exists."},
            ],
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "format": {"type": "string", "enum": ["step", "stl", "glb"]},
            },
            "required": ["session_id", "format"],
            "additionalProperties": False,
        },
        "outputSchema": export_output_schema(),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    }
]


async def export(arguments: Dict[str, Any], backend_client: Any) -> Dict[str, Any]:
    return await backend_client.export(arguments)


HANDLERS = {"export": export}
