"""Shared remote guidance surfaces for CADAgent MCP."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


SERVER_INSTRUCTIONS = """\
CADAgent MCP -- Remote CAD Operating Guide

ACTIVE MCP CONTRACT
- Tool surface is exactly: create_session, write_spec, undo_write_spec, export.
- Do not invent or request operation-level tools.
- Authoring is spec-only: host sends full part_spec to write_spec; backend performs deterministic validate -> compile -> execute.

GLOBAL OPERATING RULES
- Never hallucinate geometry, dimensions, feature success, or export availability.
- Treat tool results as authoritative. If a claim is not in structured tool output, state uncertainty.
- This MCP is not a Fusion 360 skill, script runner, or screenshot workflow.
- Never fabricate missing constraints. Ask for clarification when dimensions or manufacturability constraints materially affect the model.
- Use the returned resource_link (cadagent.co download page) as the download destination.
- Call export when you need an explicit format-specific re-export or refresh.

REMOTE GUIDANCE SURFACES
- Primary workflow guidance lives in these initialize instructions.
- Supplemental references are available at cadagent://guides/remote-usage and cadagent://guides/stale-reference-recovery.

SESSION SETUP
- Call create_session before authoring or export.
- Save and reuse the returned session_id.
- Never guess a session_id.

SPEC-ONLY AUTHORING WORKFLOW
1. Interpret user intent and restate the target part in CAD terms.
2. Identify missing constraints that materially affect geometry.
3. Build a complete PartSpec v1 payload.
4. Call write_spec with session_id + full part_spec.
5. If validation fails, inspect structuredContent.error.details.issues, correct those exact paths, and resend full part_spec.
6. For accepted results, report what changed using structured outputs and provide resource_link.
7. Offer continued iteration by editing and resubmitting a full part_spec.

CAD GENERATION WORKFLOW
1. Interpret intent and convert it to a complete PartSpec.
2. Submit via write_spec and rely on deterministic backend validation/execution.
3. If validation fails, repair exact issues and resubmit full PartSpec.
4. Share returned resource_link and offer next iteration.

MODELING WORKFLOW
1. create_session
2. write_spec (full part_spec)
3. undo_write_spec when rollback is requested
4. export when explicit format refresh is needed

PARTSPEC RULES
- write_spec requires session_id + part_spec only. Do not send prompt text or partial deltas.
- write_spec is not a natural-language prompt tool. Never send free-text instructions to write_spec.
- part_spec must be complete on every write_spec call.
- Supported feature kinds: block, cylinder, hole, countersink_hole, linear_hole_pattern, fillet, shell.
- Face selectors: top, bottom, front, back, left, right, outer_side.
- Edge selectors: outer_vertical.
- Placement reference: face_center. Pattern axes: x, y.
- Scalar fields may be literals or {"param":"parameter_name"} refs.
- IDs must be snake_case and references must target earlier feature ids.
- On PART_SPEC_VALIDATION_FAILED, fix and resubmit; do not switch to operation-style calls.

UNDO AND EXPORT
- Use undo_write_spec to restore previous full-spec snapshots.
- Use export for explicit format-specific refresh (step, stl, glb).
- Before closing a completed write_spec response, surface returned resource_link and exports.

SPATIAL STATE
- Every tool response includes spatial_state.
- mode=full: complete geometry snapshot.
- mode=delta: incremental geometry changes.
- mode=empty: no geometry exists yet.

READING GEOMETRY
- Use returned spatial_state as authoritative geometry context.
- Do not infer unreturned topology facts.

IDENTIFYING ENTITIES
- Use only ids and selectors returned or validated by the active contract.
- Do not invent ids or assume hidden operation-level identifiers.

STALE REFERENCES
- If a response reports stale/unknown references, refresh by correcting and resubmitting full PartSpec.
- For rollback, use undo_write_spec instead of patch-style edits.

COORDINATE SYSTEM
- Right-handed: X right, Y forward, Z up.
- All dimensions are millimeters.
"""

_RESOURCE_CONTENT: Dict[str, str] = {
    "cadagent://guides/remote-usage": """# CADAgent Remote MCP Usage Guide

CADAgent is designed to work as a remote MCP server that clients connect to by URL.

## Primary guidance surfaces

1. `initialize.instructions` is the primary workflow guide.
2. Tool descriptions and `x-cadagent-contract` metadata are the primary execution contracts.
3. These resources are supplemental reference material for clients that support MCP resources.

## Canonical workflow

1. `create_session`
2. `write_spec` with a complete PartSpec v1 payload
3. If validation fails, correct the full PartSpec and call `write_spec` again
4. Use `undo_write_spec` for rollback to prior full-spec snapshots
5. Use `export` for explicit format exports (`step`, `stl`, `glb`)
6. Share returned `resource_link` before concluding the response

## Guardrails

- Do not switch to Fusion-specific workflows.
- Do not guess session ids, face ids, or edge ids.
- Do not assume any operation-level MCP tool exists in this contract.
- Do not claim an export exists until write_spec or export returns the actual links.
- Treat resource_link as the user-facing cadagent.co download-page URL and download_url as the direct artifact URL.
- Do not finish a completed modeling handoff without sharing the returned resource_link URL.
- Do not treat write_spec as a text prompt endpoint; always send a full structured part_spec object.
- Do not send partial PartSpec deltas. Always submit a complete part_spec on each write_spec call.
- On validation failure, inspect `structuredContent.error.details.issues` and fix the exact paths called out.
- Tool failures return `result.isError=true` plus `structuredContent.error`; this is a recoverable tool result, not a transport disconnect.
- After completing requested model changes through write_spec, share the returned resource_link URL and offer continued iteration after the user reviews the model on the website.
""",
    "cadagent://guides/stale-reference-recovery": """# CADAgent Spec-Only Recovery

Use this guide when a write_spec submission or undo flow needs correction.

## Recovery workflow

1. Inspect `structuredContent.error` from the failing tool response.
2. For `PART_SPEC_VALIDATION_FAILED`, read `details.issues` paths and constraints.
3. Correct those exact paths in the full `part_spec`.
4. Resubmit via `write_spec` with the full corrected PartSpec.
5. If the latest edit should be reverted, call `undo_write_spec`.

## Common cases

- Required field missing: add it to full `part_spec`, then resubmit.
- Invalid selector or enum value: replace with supported contract values.
- Geometry infeasible: adjust dimensions/constraints and resubmit full `part_spec`.
""",
}

RESOURCE_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "uri": "cadagent://guides/remote-usage",
        "name": "remote-usage",
        "title": "CADAgent Remote MCP Usage Guide",
        "description": "Reference guide for using CADAgent as a remote MCP server without local Claude skills.",
        "mimeType": "text/markdown",
        "annotations": {
            "audience": ["assistant", "user"],
            "priority": 1.0,
        },
    },
    {
        "uri": "cadagent://guides/stale-reference-recovery",
        "name": "stale-reference-recovery",
        "title": "CADAgent Spec-Only Recovery",
        "description": "Reference guide for correcting full PartSpec submissions and rollback in spec-only mode.",
        "mimeType": "text/markdown",
        "annotations": {
            "audience": ["assistant", "user"],
            "priority": 0.9,
        },
    },
]


def list_resources() -> List[Dict[str, Any]]:
    return deepcopy(RESOURCE_DEFINITIONS)


def read_resource(uri: str) -> Dict[str, Any]:
    resource_uri = str(uri or "").strip()
    if resource_uri not in _RESOURCE_CONTENT:
        raise KeyError(resource_uri)
    resource = next(item for item in RESOURCE_DEFINITIONS if item["uri"] == resource_uri)
    return {
        "contents": [
            {
                "uri": resource_uri,
                "mimeType": resource["mimeType"],
                "text": _RESOURCE_CONTENT[resource_uri],
                "annotations": deepcopy(resource.get("annotations", {})),
            }
        ]
    }


__all__ = ["RESOURCE_DEFINITIONS", "SERVER_INSTRUCTIONS", "list_resources", "read_resource"]
