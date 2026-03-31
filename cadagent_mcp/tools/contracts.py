"""Shared MCP tool output schemas and examples."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional


VECTOR3_SCHEMA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}

NULLABLE_STRING_SCHEMA = {"type": ["string", "null"]}
NULLABLE_BBOX_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "min": deepcopy(VECTOR3_SCHEMA),
        "max": deepcopy(VECTOR3_SCHEMA),
    },
    "required": ["min", "max"],
    "additionalProperties": False,
}
NULLABLE_DIMENSIONS_SCHEMA = {
    "type": ["array", "null"],
    "items": {"type": "number"},
    "minItems": 3,
    "maxItems": 3,
}
STRING_LIST_SCHEMA = {"type": "array", "items": {"type": "string"}}
PREFERRED_FACE_TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "hint": {"type": "string"},
        "label": {"type": "string"},
        "face_ids": deepcopy(STRING_LIST_SCHEMA),
    },
    "required": ["hint", "label", "face_ids"],
    "additionalProperties": False,
}
PREFERRED_EDGE_TARGET_SCHEMA = {
    "type": "object",
    "properties": {
        "hint": {"type": "string"},
        "edge_ids": deepcopy(STRING_LIST_SCHEMA),
    },
    "required": ["hint", "edge_ids"],
    "additionalProperties": False,
}


def inspection_hints_properties() -> Dict[str, Dict[str, Any]]:
    return {
        "semantic_hints": deepcopy(STRING_LIST_SCHEMA),
        "semantic_face_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "face_id": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["face_id", "label"],
                "additionalProperties": False,
            },
        },
        "face_id_hints": deepcopy(STRING_LIST_SCHEMA),
        "edge_id_hints": deepcopy(STRING_LIST_SCHEMA),
        "top_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "bottom_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "front_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "back_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "outer_side_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "hole_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "preferred_face_targets": {"type": "array", "items": deepcopy(PREFERRED_FACE_TARGET_SCHEMA)},
        "linear_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "non_linear_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "vertical_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "horizontal_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "top_perimeter_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "bottom_perimeter_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "outer_side_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "hole_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "preferred_edge_targets": {"type": "array", "items": deepcopy(PREFERRED_EDGE_TARGET_SCHEMA)},
    }


def inspection_hints_required_fields() -> list[str]:
    return []

FACE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "entity_ref": {"type": "string"},
        "kind": {"type": "string"},
        "normal": deepcopy(VECTOR3_SCHEMA),
        "centroid_mm": deepcopy(VECTOR3_SCHEMA),
        "area_mm2": {"type": "number"},
        "body_id": {"type": "string"},
        "semantic_label": {"type": "string"},
        "loop_edge_ids": deepcopy(STRING_LIST_SCHEMA),
    },
    "required": ["id", "kind", "normal", "centroid_mm", "area_mm2", "body_id"],
    "additionalProperties": False,
}

EDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "entity_ref": {"type": "string"},
        "kind": {"type": "string"},
        "midpoint_mm": deepcopy(VECTOR3_SCHEMA),
        "direction": deepcopy(VECTOR3_SCHEMA),
        "length_mm": {"type": "number"},
        "body_id": {"type": "string"},
        "adjacent_face_ids": deepcopy(STRING_LIST_SCHEMA),
    },
    "required": ["id", "kind", "midpoint_mm", "direction", "length_mm", "body_id"],
    "additionalProperties": False,
}

SPATIAL_STATE_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["full", "delta", "empty"]},
        "scene_revision": {"type": "integer"},
        "topology_changed": {"type": "boolean"},
        "body_id": deepcopy(NULLABLE_STRING_SCHEMA),
        "bbox_mm": deepcopy(NULLABLE_BBOX_SCHEMA),
        "dimensions_mm": deepcopy(NULLABLE_DIMENSIONS_SCHEMA),
        "faces": {"type": "array", "items": deepcopy(FACE_SCHEMA)},
        "edges": {"type": "array", "items": deepcopy(EDGE_SCHEMA)},
        "added_faces": {"type": "array", "items": deepcopy(FACE_SCHEMA)},
        "removed_face_ids": deepcopy(STRING_LIST_SCHEMA),
        "modified_faces": {"type": "array", "items": deepcopy(FACE_SCHEMA)},
        "added_edges": {"type": "array", "items": deepcopy(EDGE_SCHEMA)},
        "removed_edge_ids": deepcopy(STRING_LIST_SCHEMA),
        "modified_edges": {"type": "array", "items": deepcopy(EDGE_SCHEMA)},
    },
    "required": ["mode", "scene_revision", "topology_changed"],
    "additionalProperties": False,
}

EXAMPLE_BBOX_MM = {"min": [0.0, 0.0, 0.0], "max": [50.0, 50.0, 50.0]}
EXAMPLE_DIMENSIONS_MM = [50.0, 50.0, 50.0]
EXAMPLE_FACE = {
    "id": "face_0",
    "entity_ref": "face_0",
    "kind": "plane",
    "normal": [0.0, 0.0, 1.0],
    "centroid_mm": [25.0, 25.0, 50.0],
    "area_mm2": 2500.0,
    "body_id": "body_0",
    "semantic_label": "top_face",
    "loop_edge_ids": ["edge_0", "edge_1", "edge_2", "edge_3"],
}
EXAMPLE_EDGE = {
    "id": "edge_0",
    "entity_ref": "edge_0",
    "kind": "line",
    "midpoint_mm": [25.0, 0.0, 50.0],
    "direction": [1.0, 0.0, 0.0],
    "length_mm": 50.0,
    "body_id": "body_0",
    "adjacent_face_ids": ["face_0", "face_2"],
}
EXAMPLE_FULL_SPATIAL_STATE = {
    "mode": "full",
    "scene_revision": 4,
    "topology_changed": True,
    "body_id": "body_0",
    "bbox_mm": deepcopy(EXAMPLE_BBOX_MM),
    "dimensions_mm": list(EXAMPLE_DIMENSIONS_MM),
    "faces": [deepcopy(EXAMPLE_FACE)],
    "edges": [deepcopy(EXAMPLE_EDGE)],
}
EXAMPLE_EMPTY_SPATIAL_STATE = {
    "mode": "empty",
    "scene_revision": 0,
    "topology_changed": False,
    "body_id": None,
    "bbox_mm": None,
    "dimensions_mm": None,
}
EXAMPLE_DELTA_SPATIAL_STATE = {
    "mode": "delta",
    "scene_revision": 5,
    "topology_changed": False,
    "body_id": "body_0",
    "bbox_mm": deepcopy(EXAMPLE_BBOX_MM),
    "dimensions_mm": list(EXAMPLE_DIMENSIONS_MM),
    "added_faces": [],
    "removed_face_ids": [],
    "modified_faces": [deepcopy(EXAMPLE_FACE)],
    "added_edges": [],
    "removed_edge_ids": [],
    "modified_edges": [deepcopy(EXAMPLE_EDGE)],
}


def mutation_output_schema(
    *,
    extra_properties: Optional[Dict[str, Dict[str, Any]]] = None,
    required_extra: Optional[list[str]] = None,
) -> Dict[str, Any]:
    properties: Dict[str, Dict[str, Any]] = {
        "session_id": {"type": "string"},
        "operation_id": {"type": "string"},
        "scene_revision": {"type": "integer"},
        "topology_changed": {"type": "boolean"},
        "stale_references_possible": {"type": "boolean"},
        "body_id": deepcopy(NULLABLE_STRING_SCHEMA),
        "bbox_mm": deepcopy(NULLABLE_BBOX_SCHEMA),
        "dimensions_mm": deepcopy(NULLABLE_DIMENSIONS_SCHEMA),
        "faces": {"type": "array", "items": deepcopy(FACE_SCHEMA)},
        "edges": {"type": "array", "items": deepcopy(EDGE_SCHEMA)},
        "summary": {"type": "string"},
        "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
    }
    if extra_properties:
        for key, value in extra_properties.items():
            properties[key] = deepcopy(value)

    required = ["session_id", "operation_id", "summary", "spatial_state"]
    if required_extra:
        required.extend(required_extra)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


def create_session_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "expires_at": {"type": "string"},
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
        },
        "required": ["session_id", "expires_at", "status", "summary", "spatial_state"],
        "additionalProperties": False,
    }


def face_inventory_output_schema() -> Dict[str, Any]:
    properties = {
        "session_id": {"type": "string"},
        "faces": {"type": "array", "items": deepcopy(FACE_SCHEMA)},
        "scene_revision": {"type": "integer"},
        "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
    }
    properties.update(inspection_hints_properties())

    return {
        "type": "object",
        "properties": properties,
        "required": ["session_id", "faces", "scene_revision", "spatial_state", *inspection_hints_required_fields()],
        "additionalProperties": False,
    }


def edge_inventory_output_schema() -> Dict[str, Any]:
    properties = {
        "session_id": {"type": "string"},
        "edges": {"type": "array", "items": deepcopy(EDGE_SCHEMA)},
        "scene_revision": {"type": "integer"},
        "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
    }
    properties.update(inspection_hints_properties())

    return {
        "type": "object",
        "properties": properties,
        "required": ["session_id", "edges", "scene_revision", "spatial_state", *inspection_hints_required_fields()],
        "additionalProperties": False,
    }


def body_summary_output_schema() -> Dict[str, Any]:
    properties = {
        "session_id": {"type": "string"},
        "body_id": deepcopy(NULLABLE_STRING_SCHEMA),
        "bbox_mm": deepcopy(NULLABLE_BBOX_SCHEMA),
        "dimensions_mm": deepcopy(NULLABLE_DIMENSIONS_SCHEMA),
        "body_count": {"type": "integer"},
        "face_count": {"type": "integer"},
        "edge_count": {"type": "integer"},
        "last_operation_id": deepcopy(NULLABLE_STRING_SCHEMA),
        "last_scene_revision": {"type": "integer"},
        "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
    }
    properties.update(inspection_hints_properties())

    return {
        "type": "object",
        "properties": properties,
        "required": [
            "session_id",
            "body_id",
            "body_count",
            "face_count",
            "edge_count",
            *inspection_hints_required_fields(),
            "last_scene_revision",
            "spatial_state",
        ],
        "additionalProperties": False,
    }


def export_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "format": {"type": "string", "enum": ["step", "stl", "glb"]},
            "resource_link": {"type": "string"},
            "download_url": {"type": "string"},
            "expires_at": {"type": "string"},
            "content": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["type", "text"],
                    "additionalProperties": False,
                },
            },
            "spatial_state": deepcopy(SPATIAL_STATE_SCHEMA),
        },
        "required": [
            "session_id",
            "format",
            "resource_link",
            "download_url",
            "expires_at",
            "content",
            "spatial_state",
        ],
        "additionalProperties": False,
    }


__all__ = [
    "EDGE_SCHEMA",
    "EXAMPLE_DELTA_SPATIAL_STATE",
    "EXAMPLE_EDGE",
    "EXAMPLE_EMPTY_SPATIAL_STATE",
    "EXAMPLE_FACE",
    "EXAMPLE_FULL_SPATIAL_STATE",
    "FACE_SCHEMA",
    "SPATIAL_STATE_SCHEMA",
    "body_summary_output_schema",
    "create_session_output_schema",
    "edge_inventory_output_schema",
    "export_output_schema",
    "face_inventory_output_schema",
    "mutation_output_schema",
]
