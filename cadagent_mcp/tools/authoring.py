"""PartSpec-first authoring tools for MCP."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from .contracts import mutation_output_schema
from .metadata import tool_contract


def _load_partspec_contract_module() -> Any:
    fallback_contract = SimpleNamespace(
        PART_SPEC_V1_VERSION="1.0",
        PART_SPEC_V1_UNITS="mm",
        PART_SPEC_V1_FACE_SEMANTICS=("top", "bottom", "front", "back", "left", "right", "outer_side"),
        PART_SPEC_V1_EDGE_SELECTORS=("outer_vertical",),
        PART_SPEC_V1_PATTERN_AXES=("x", "y"),
        PART_SPEC_V1_PLACEMENT_REFERENCES=("face_center",),
        PART_SPEC_V1_SOLID_OPERATIONS=("new", "join", "cut", "intersect"),
    )
    try:
        from backend.spec_compiler import contract as contract_module  # type: ignore

        return contract_module
    except Exception:
        contract_candidates = (
            Path(__file__).resolve().parents[4]
            / "cadagent-main"
            / "backend"
            / "backend"
            / "spec_compiler"
            / "contract.py",
            Path.cwd() / "cadagent-main" / "backend" / "backend" / "spec_compiler" / "contract.py",
        )
        for contract_path in contract_candidates:
            if not contract_path.exists():
                continue
            spec = importlib.util.spec_from_file_location("cadagent_partspec_contract", contract_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        return fallback_contract


_CONTRACT = _load_partspec_contract_module()
_PART_SPEC_VERSION = str(_CONTRACT.PART_SPEC_V1_VERSION)
_PART_SPEC_UNITS = str(_CONTRACT.PART_SPEC_V1_UNITS)
_FACE_SEMANTICS = tuple(_CONTRACT.PART_SPEC_V1_FACE_SEMANTICS)
_EDGE_SELECTORS = tuple(_CONTRACT.PART_SPEC_V1_EDGE_SELECTORS)
_PATTERN_AXES = tuple(_CONTRACT.PART_SPEC_V1_PATTERN_AXES)
_PLACEMENT_REFERENCES = tuple(_CONTRACT.PART_SPEC_V1_PLACEMENT_REFERENCES)
_SOLID_OPERATIONS = tuple(_CONTRACT.PART_SPEC_V1_SOLID_OPERATIONS)
_SNAKE_CASE = r"^[a-z][a-z0-9_]*$"


def _part_spec_scalar_ref_schema() -> Dict[str, Any]:
    return {
        "anyOf": [
            {"type": "number"},
            {
                "type": "object",
                "properties": {"param": {"type": "string", "pattern": _SNAKE_CASE}},
                "required": ["param"],
                "additionalProperties": False,
            },
        ]
    }


def _part_spec_schema() -> Dict[str, Any]:
    scalar_ref = _part_spec_scalar_ref_schema()
    depth_ref = {
        "anyOf": [
            {"type": "string", "enum": ["through_all"]},
            scalar_ref,
        ]
    }
    target_schema = {
        "type": "object",
        "properties": {
            "body": {"type": "string", "pattern": _SNAKE_CASE},
            "face": {"type": "string", "enum": list(_FACE_SEMANTICS)},
        },
        "required": ["body", "face"],
        "additionalProperties": False,
    }
    placement_schema = {
        "type": "object",
        "properties": {
            "reference": {"type": "string", "enum": list(_PLACEMENT_REFERENCES)},
            "offset": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
        },
        "required": ["reference", "offset"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "spec_version": {"type": "string", "enum": [_PART_SPEC_VERSION]},
            "units": {"type": "string", "enum": [_PART_SPEC_UNITS]},
            "part": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "pattern": _SNAKE_CASE},
                    "name": {"type": "string", "minLength": 1},
                    "summary": {"type": "string", "minLength": 1},
                },
                "required": ["id", "name", "summary"],
                "additionalProperties": False,
            },
            "parameters": {
                "type": "object",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["number", "integer", "boolean", "string"]},
                        "value": {},
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "description": {"type": "string"},
                    },
                    "required": ["type", "value"],
                    "additionalProperties": False,
                },
            },
            "features": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "oneOf": [
                        {"$ref": "#/$defs/block"},
                        {"$ref": "#/$defs/cylinder"},
                        {"$ref": "#/$defs/hole"},
                        {"$ref": "#/$defs/countersink_hole"},
                        {"$ref": "#/$defs/linear_hole_pattern"},
                        {"$ref": "#/$defs/fillet"},
                        {"$ref": "#/$defs/shell"},
                    ]
                },
            },
        },
        "required": ["spec_version", "units", "part", "parameters", "features"],
        "additionalProperties": False,
        "$defs": {
            "feature_id": {"type": "string", "pattern": _SNAKE_CASE},
            "origin": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
                "required": ["x", "y", "z"],
                "additionalProperties": False,
            },
            "block": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "block"},
                    "operation": {"type": "string", "enum": list(_SOLID_OPERATIONS)},
                    "size": {
                        "type": "object",
                        "properties": {"x": scalar_ref, "y": scalar_ref, "z": scalar_ref},
                        "required": ["x", "y", "z"],
                        "additionalProperties": False,
                    },
                    "placement": {
                        "type": "object",
                        "properties": {
                            "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]},
                            "origin": {"$ref": "#/$defs/origin"},
                        },
                        "required": ["plane", "origin"],
                        "additionalProperties": False,
                    },
                },
                "required": ["id", "kind", "operation", "size", "placement"],
                "additionalProperties": False,
            },
            "cylinder": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "cylinder"},
                    "operation": {"type": "string", "enum": list(_SOLID_OPERATIONS)},
                    "radius": scalar_ref,
                    "height": scalar_ref,
                    "placement": {
                        "type": "object",
                        "properties": {
                            "plane": {"type": "string", "enum": ["XY", "XZ", "YZ"]},
                            "origin": {"$ref": "#/$defs/origin"},
                        },
                        "required": ["plane", "origin"],
                        "additionalProperties": False,
                    },
                },
                "required": ["id", "kind", "operation", "radius", "height", "placement"],
                "additionalProperties": False,
            },
            "hole": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "hole"},
                    "target": target_schema,
                    "placement": placement_schema,
                    "diameter": scalar_ref,
                    "depth": depth_ref,
                },
                "required": ["id", "kind", "target", "placement", "diameter", "depth"],
                "additionalProperties": False,
            },
            "countersink_hole": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "countersink_hole"},
                    "target": target_schema,
                    "placement": placement_schema,
                    "diameter": scalar_ref,
                    "depth": depth_ref,
                    "countersink_diameter": scalar_ref,
                    "countersink_angle": scalar_ref,
                },
                "required": [
                    "id",
                    "kind",
                    "target",
                    "placement",
                    "diameter",
                    "depth",
                    "countersink_diameter",
                    "countersink_angle",
                ],
                "additionalProperties": False,
            },
            "linear_hole_pattern": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "linear_hole_pattern"},
                    "target": target_schema,
                    "placement": placement_schema,
                    "hole": {
                        "type": "object",
                        "properties": {"diameter": scalar_ref, "depth": depth_ref},
                        "required": ["diameter", "depth"],
                        "additionalProperties": False,
                    },
                    "pattern": {
                        "type": "object",
                        "properties": {
                            "axis": {"type": "string", "enum": list(_PATTERN_AXES)},
                            "count": {"type": "integer", "minimum": 1},
                            "spacing": scalar_ref,
                        },
                        "required": ["axis", "count", "spacing"],
                        "additionalProperties": False,
                    },
                },
                "required": ["id", "kind", "target", "placement", "hole", "pattern"],
                "additionalProperties": False,
            },
            "fillet": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "fillet"},
                    "target": {
                        "type": "object",
                        "properties": {
                            "body": {"type": "string", "pattern": _SNAKE_CASE},
                            "edges": {"type": "string", "enum": list(_EDGE_SELECTORS)},
                        },
                        "required": ["body", "edges"],
                        "additionalProperties": False,
                    },
                    "radius": scalar_ref,
                },
                "required": ["id", "kind", "target", "radius"],
                "additionalProperties": False,
            },
            "shell": {
                "type": "object",
                "properties": {
                    "id": {"$ref": "#/$defs/feature_id"},
                    "kind": {"const": "shell"},
                    "target": {
                        "type": "object",
                        "properties": {"body": {"type": "string", "pattern": _SNAKE_CASE}},
                        "required": ["body"],
                        "additionalProperties": False,
                    },
                    "remove_faces": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(_FACE_SEMANTICS)},
                        "minItems": 1,
                    },
                    "thickness": scalar_ref,
                },
                "required": ["id", "kind", "target", "remove_faces", "thickness"],
                "additionalProperties": False,
            },
        },
    }


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "write_spec",
        "title": "Write Spec",
        **tool_contract(
            summary="Author a new or edited part from a host-generated PartSpec (PartSpec -> validated IR -> build execution).",
            when_to_use="Use this for net-new part authoring and full-spec edits where the host can supply a complete PartSpec v1 object.",
            when_not_to_use="Do not use this as a natural-language prompt endpoint or for partial/delta patch payloads.",
            authoritative_result="generated_part_spec, ir_document, scene_revision, topology_changed, spatial_state, resource_link, and exports define the authoritative model and download state.",
            follow_up="Use returned resource_link (cadagent.co download page) as the download destination, then continue with a full modified part_spec edit or explicit export.",
            failure_handling="If validation or execution fails, read structured issues, fix part_spec, and resubmit the full payload.",
            input_field_semantics={
                "session_id": "Active CADAgent modeling session.",
                "part_spec": "Full PartSpec v1 object generated by the host and validated by deterministic backend checks. Never send natural-language prompt text here. On failure, inspect structuredContent.error.details.issues and correct those exact paths before resubmitting the full payload.",
                "allow_large_regen": "When true, allows broad spec regeneration without UNEXPECTED_LARGE_SPEC_DELTA warning.",
            },
            output_field_semantics={
                "mode": "Always 'spec' for this tool.",
                "generated_part_spec": "Canonical submitted PartSpec payload used for deterministic compilation.",
                "ir_document": "Validated IR document executed by the backend target adapter.",
                "operation_count": "Count of executed IR operations.",
                "spatial_state": "Ground-truth geometry snapshot for follow-up reasoning.",
                "resource_link": "Format-agnostic cadagent.co download-page URL for this session.",
                "exports": "Available export artifacts generated automatically for the completed model.",
            },
            follow_up_tools=["write_spec", "undo_write_spec", "export"],
            common_failures=[
                {"code": "PART_SPEC_VALIDATION_FAILED", "recovery": "Fix the indicated part_spec fields and resubmit the full payload."},
                {"code": "IR_VALIDATION_FAILED", "recovery": "Correct generated constraints and retry authoring."},
                {"code": "BACKEND_EXECUTION_FAILED", "recovery": "Adjust part_spec constraints and retry with feasible geometry."},
            ],
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "part_spec": _part_spec_schema(),
                "allow_large_regen": {"type": "boolean", "default": False},
            },
            "required": ["session_id", "part_spec"],
            "additionalProperties": False,
        },
        "outputSchema": mutation_output_schema(
            extra_properties={
                "request_id": {"type": ["string", "null"]},
                "mode": {"type": "string", "enum": ["spec"]},
                "generated_part_spec": {"type": "object"},
                "ir_document": {"type": "object"},
                "operation_count": {"type": "integer"},
                "resource_link": {"type": "string"},
                "exports": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "format": {"type": "string", "enum": ["step", "stl", "glb"]},
                            "download_url": {"type": "string"},
                            "resource_link": {"type": "string"},
                            "expires_at": {"type": "string"},
                        },
                        "required": ["format", "download_url", "resource_link", "expires_at"],
                        "additionalProperties": False,
                    },
                },
                "auto_export": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "formats_requested": {"type": "array", "items": {"type": "string"}},
                        "formats_succeeded": {"type": "array", "items": {"type": "string"}},
                        "formats_failed": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["enabled", "formats_requested", "formats_succeeded", "formats_failed"],
                    "additionalProperties": False,
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            required_extra=["mode", "generated_part_spec", "ir_document", "operation_count", "scene_revision", "resource_link", "exports", "auto_export"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    },
    {
        "name": "undo_write_spec",
        "title": "Undo Part Authoring",
        **tool_contract(
            summary="Undo one or more PartSpec authoring edits and restore a previous executed spec snapshot.",
            when_to_use="Use this when the latest PartSpec edit over-modified the model and should be rolled back.",
            when_not_to_use="Do not use this to create a new variation; use write_spec with an updated full part_spec instead.",
            authoritative_result="restored_part_spec, ir_document, scene_revision, topology_changed, and spatial_state define the restored model state.",
            follow_up="Continue editing with a corrected full part_spec via write_spec, or export the restored model.",
            failure_handling="If no snapshots are available, surface NO_PART_SPEC_HISTORY without fallback behavior.",
            input_field_semantics={
                "session_id": "Active CADAgent modeling session.",
                "steps": "Undo depth; 1 restores the immediately previous PartSpec snapshot.",
            },
            output_field_semantics={
                "restored_part_spec": "Canonical PartSpec snapshot restored and re-executed.",
                "ir_document": "IR document compiled from restored_part_spec.",
                "operation_count": "Count of IR operations executed during undo replay.",
            },
            follow_up_tools=["write_spec", "export"],
            common_failures=[
                {"code": "NO_PART_SPEC_HISTORY", "recovery": "Create/edit at least one PartSpec before calling undo."},
                {"code": "PART_SPEC_VALIDATION_FAILED", "recovery": "Author a corrected PartSpec and execute it."},
                {"code": "BACKEND_EXECUTION_FAILED", "recovery": "Author a corrected PartSpec and retry."},
            ],
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "steps": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
        "outputSchema": mutation_output_schema(
            extra_properties={
                "request_id": {"type": ["string", "null"]},
                "mode": {"type": "string", "enum": ["spec"]},
                "restored_part_spec": {"type": "object"},
                "ir_document": {"type": "object"},
                "operation_count": {"type": "integer"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            required_extra=["mode", "restored_part_spec", "ir_document", "operation_count", "scene_revision"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False},
    },
]


async def write_spec(arguments: Dict[str, Any], backend_client: Any) -> Dict[str, Any]:
    return await backend_client.write_spec(arguments)


async def undo_write_spec(arguments: Dict[str, Any], backend_client: Any) -> Dict[str, Any]:
    return await backend_client.undo_write_spec(arguments)


HANDLERS = {"write_spec": write_spec, "undo_write_spec": undo_write_spec}
