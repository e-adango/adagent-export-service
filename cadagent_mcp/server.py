"""Remote streamable-HTTP MCP server for CADAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from .backend_client import (
    BackendClient,
    BackendMCPError,
    backend_error_to_tool_result,
    backend_error_to_tool_text,
)
from .guidance_registry import SERVER_INSTRUCTIONS, list_resources, read_resource
from .tool_registry import TOOL_DEFINITIONS, call_tool

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"
SESSION_HEADER = "Mcp-Session-Id"
PROTOCOL_HEADER = "MCP-Protocol-Version"


@dataclass
class TransportSession:
    session_id: str


def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _summary_text(tool_name: str, payload: Dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    if tool_name == "create_session":
        session_id = str(payload.get("session_id") or "").strip()
        if summary and session_id:
            return f"{summary} session_id={session_id}"
        if session_id:
            return f"Session created: {session_id}"
        return summary or "Session created."
    if tool_name == "export":
        base = f"Export ready: {payload.get('resource_link', '')}"
        digest = _spatial_digest(payload)
        return f"{base} [{digest}]" if digest else base
    base = summary or f"{tool_name} completed."
    digest = _spatial_digest(payload)
    return f"{base} [{digest}]" if digest else base


def _internal_tool_error_result(
    tool_name: str,
    *,
    detail: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    message = str(detail or "").strip() or "Tool execution failed."
    error_payload: Dict[str, Any] = {
        "isError": True,
        "error": {
            "source": "cadagent-mcp",
            "code": "MCP_TOOL_EXECUTION_FAILED",
            "category": "mcp_internal_error",
            "message": message,
        },
    }
    if request_id:
        error_payload["error"]["request_id"] = request_id
    return {
        "content": [{"type": "text", "text": f"{tool_name} failed (MCP_TOOL_EXECUTION_FAILED): {message}"}],
        "structuredContent": error_payload,
        "isError": True,
    }


def _spatial_digest(payload: Dict[str, Any]) -> str:
    parts = []
    session_id = str(payload.get("session_id") or "").strip()
    if session_id:
        parts.append(f"session_id={session_id}")

    spatial_state = payload.get("spatial_state")
    if isinstance(spatial_state, dict):
        mode = str(spatial_state.get("mode") or "").strip()
        if mode:
            parts.append(f"mode={mode}")
        scene_revision = spatial_state.get("scene_revision")
        if scene_revision is not None:
            parts.append(f"scene_revision={scene_revision}")
        topo = spatial_state.get("topology_changed")
        if isinstance(topo, bool):
            parts.append(f"topology_changed={str(topo).lower()}")

    if payload.get("body_count") is not None:
        parts.append(f"body_count={payload.get('body_count')}")

    face_count = payload.get("face_count")
    if face_count is None and isinstance(payload.get("faces"), list):
        face_count = len(payload["faces"])
    if face_count is not None:
        parts.append(f"face_count={face_count}")

    edge_count = payload.get("edge_count")
    if edge_count is None and isinstance(payload.get("edges"), list):
        edge_count = len(payload["edges"])
    if edge_count is not None:
        parts.append(f"edge_count={edge_count}")

    body_id = payload.get("body_id")
    if body_id is not None:
        parts.append(f"body_id={body_id}")

    dimensions = payload.get("dimensions_mm")
    if isinstance(dimensions, list) and len(dimensions) == 3:
        parts.append(f"dims_mm={[round(float(v), 3) for v in dimensions]}")

    semantic_hints = payload.get("semantic_hints")
    if isinstance(semantic_hints, list) and semantic_hints:
        preview = [str(v) for v in semantic_hints[:4]]
        suffix = "..." if len(semantic_hints) > 4 else ""
        parts.append(f"semantic_hints={preview}{suffix}")

    semantic_face_refs = payload.get("semantic_face_refs")
    if isinstance(semantic_face_refs, list) and semantic_face_refs:
        preview_pairs = []
        for item in semantic_face_refs[:4]:
            if not isinstance(item, dict):
                continue
            face_id = str(item.get("face_id") or "").strip()
            label = str(item.get("label") or "").strip()
            if face_id and label:
                preview_pairs.append(f"{face_id}:{label}")
        if preview_pairs:
            suffix = "..." if len(semantic_face_refs) > len(preview_pairs) else ""
            parts.append(f"semantic_face_refs={preview_pairs}{suffix}")

    face_id_hints = payload.get("face_id_hints")
    if isinstance(face_id_hints, list) and face_id_hints:
        preview = [str(v) for v in face_id_hints[:4]]
        suffix = "..." if len(face_id_hints) > 4 else ""
        parts.append(f"face_id_hints={preview}{suffix}")
        parts.append("face_id_format=face_N")

    edge_id_hints = payload.get("edge_id_hints")
    if isinstance(edge_id_hints, list) and edge_id_hints:
        preview = [str(v) for v in edge_id_hints[:4]]
        suffix = "..." if len(edge_id_hints) > 4 else ""
        parts.append(f"edge_id_hints={preview}{suffix}")
        parts.append("edge_id_format=edge_N")

    for field in [
        "top_face_ids",
        "bottom_face_ids",
        "front_face_ids",
        "back_face_ids",
        "outer_side_face_ids",
        "hole_face_ids",
    ]:
        values = payload.get(field)
        if isinstance(values, list) and values:
            preview = [str(v) for v in values[:4]]
            suffix = "..." if len(values) > 4 else ""
            parts.append(f"{field}={preview}{suffix}")

    for field in [
        "linear_edge_ids",
        "non_linear_edge_ids",
        "vertical_edge_ids",
        "horizontal_edge_ids",
        "top_perimeter_edge_ids",
        "bottom_perimeter_edge_ids",
        "outer_side_edge_ids",
        "hole_edge_ids",
    ]:
        values = payload.get(field)
        if isinstance(values, list) and values:
            preview = [str(v) for v in values[:4]]
            suffix = "..." if len(values) > 4 else ""
            parts.append(f"{field}={preview}{suffix}")

    preferred_face_targets = payload.get("preferred_face_targets")
    if isinstance(preferred_face_targets, list) and preferred_face_targets:
        preview = []
        for item in preferred_face_targets[:3]:
            if not isinstance(item, dict):
                continue
            hint = str(item.get("hint") or "").strip()
            face_ids = item.get("face_ids")
            if not hint or not isinstance(face_ids, list) or not face_ids:
                continue
            preview.append(f"{hint}:{str(face_ids[0])}")
        if preview:
            suffix = "..." if len(preferred_face_targets) > len(preview) else ""
            parts.append(f"preferred_face_targets={preview}{suffix}")

    preferred_edge_targets = payload.get("preferred_edge_targets")
    if isinstance(preferred_edge_targets, list) and preferred_edge_targets:
        preview = []
        for item in preferred_edge_targets[:3]:
            if not isinstance(item, dict):
                continue
            hint = str(item.get("hint") or "").strip()
            edge_ids = item.get("edge_ids")
            if not hint or not isinstance(edge_ids, list) or not edge_ids:
                continue
            preview.append(f"{hint}:{str(edge_ids[0])}")
        if preview:
            suffix = "..." if len(preferred_edge_targets) > len(preview) else ""
            parts.append(f"preferred_edge_targets={preview}{suffix}")

    return "; ".join(parts)


def _has_required_accept_for_post(header_value: str) -> bool:
    accept = str(header_value or "").lower()
    return "application/json" in accept and "text/event-stream" in accept


def _validate_protocol_header(request: Request) -> str:
    version = (request.headers.get(PROTOCOL_HEADER) or "").strip()
    if not version:
        return "2025-03-26"
    if version != SUPPORTED_PROTOCOL_VERSION:
        raise HTTPException(status_code=400, detail=f"Unsupported {PROTOCOL_HEADER}: {version}")
    return version


def create_app(backend_base_url: Optional[str] = None) -> FastAPI:
    backend_url = (backend_base_url or os.environ.get("CADAGENT_BACKEND_URL") or "http://localhost:8000").rstrip("/")
    backend_client = BackendClient(backend_url)
    sessions: Dict[str, TransportSession] = {}

    app = FastAPI(title="CADAgent MCP Server", version="0.2.0")

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "service": "cadagent-mcp", "backend_url": backend_url}

    @app.post("/mcp")
    async def mcp_post(request: Request):
        _validate_protocol_header(request)
        accept_header = request.headers.get("accept") or request.headers.get("Accept") or ""
        if not _has_required_accept_for_post(accept_header):
            raise HTTPException(status_code=406, detail="Accept must include application/json and text/event-stream.")

        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="POST body must be a JSON object.")

        method = payload.get("method")
        request_id = payload.get("id")
        has_method = isinstance(method, str) and bool(str(method).strip())
        is_notification = has_method and ("id" not in payload or payload.get("id") is None)

        session_id = (request.headers.get(SESSION_HEADER) or "").strip() or None

        if has_method and str(method).strip() == "initialize":
            if is_notification:
                return JSONResponse(_jsonrpc_error(request_id, -32600, "initialize must be a request with id."), status_code=400)
            new_session_id = uuid4().hex
            sessions[new_session_id] = TransportSession(session_id=new_session_id)
            response = JSONResponse(
                _jsonrpc_result(
                    request_id,
                    {
                        "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
                        "serverInfo": {"name": "cadagent-mcp", "version": "0.2.0"},
                        "capabilities": {"tools": {}, "resources": {"listChanged": False}},
                        "instructions": SERVER_INSTRUCTIONS,
                    },
                ),
                status_code=200,
            )
            response.headers[SESSION_HEADER] = new_session_id
            response.headers[PROTOCOL_HEADER] = SUPPORTED_PROTOCOL_VERSION
            return response

        if not session_id:
            raise HTTPException(status_code=400, detail=f"Missing {SESSION_HEADER} header.")
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="MCP session not found.")

        if not has_method:
            return Response(status_code=202)

        method_name = str(method).strip()
        raw_params = payload.get("params")
        params: Dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

        if is_notification:
            # Includes notifications/initialized and other client notifications.
            return Response(status_code=202)

        if method_name == "ping":
            return JSONResponse(_jsonrpc_result(request_id, {"pong": True}), status_code=200)

        if method_name == "tools/list":
            return JSONResponse(_jsonrpc_result(request_id, {"tools": TOOL_DEFINITIONS}), status_code=200)

        if method_name == "resources/list":
            return JSONResponse(_jsonrpc_result(request_id, {"resources": list_resources()}), status_code=200)

        if method_name == "resources/read":
            resource_uri = str(params.get("uri") or "").strip()
            if not resource_uri:
                return JSONResponse(_jsonrpc_error(request_id, -32602, "Missing resource uri."), status_code=400)
            try:
                resource = read_resource(resource_uri)
            except KeyError:
                return JSONResponse(
                    _jsonrpc_error(request_id, -32002, "Resource not found", {"uri": resource_uri}),
                    status_code=404,
                )
            return JSONResponse(_jsonrpc_result(request_id, resource), status_code=200)

        if method_name == "tools/call":
            tool_name = str(params.get("name") or "").strip()
            raw_arguments = params.get("arguments")
            arguments: Dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            if not tool_name:
                return JSONResponse(_jsonrpc_error(request_id, -32602, "Missing tool name."), status_code=400)
            try:
                result = await call_tool(tool_name, arguments, backend_client)
            except KeyError:
                return JSONResponse(_jsonrpc_error(request_id, -32601, f"Unknown tool '{tool_name}'."), status_code=404)
            except BackendMCPError as exc:
                tool_error = backend_error_to_tool_result(
                    exc,
                    fallback_request_id=str(request_id).strip() if request_id is not None else None,
                )
                return JSONResponse(
                    _jsonrpc_result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": backend_error_to_tool_text(tool_name, tool_error)}],
                            "structuredContent": tool_error,
                            "isError": True,
                        },
                    ),
                    status_code=200,
                )
            except Exception as exc:
                return JSONResponse(
                    _jsonrpc_result(
                        request_id,
                        _internal_tool_error_result(
                            tool_name,
                            detail=str(exc),
                            request_id=str(request_id).strip() if request_id is not None else None,
                        ),
                    ),
                    status_code=200,
                )

            return JSONResponse(
                _jsonrpc_result(
                    request_id,
                    {
                        "content": [{"type": "text", "text": _summary_text(tool_name, result)}],
                        "structuredContent": result,
                    },
                ),
                status_code=200,
            )

        return JSONResponse(_jsonrpc_error(request_id, -32601, f"Unknown method '{method_name}'."), status_code=404)

    @app.get("/mcp")
    async def mcp_get(request: Request):
        _validate_protocol_header(request)
        accept_header = request.headers.get("accept") or request.headers.get("Accept") or ""
        if "text/event-stream" not in str(accept_header).lower():
            raise HTTPException(status_code=406, detail="Accept must include text/event-stream for GET.")
        # This server currently does not support server-initiated SSE streams.
        return PlainTextResponse("SSE stream is not offered on this endpoint.", status_code=405)

    @app.delete("/mcp")
    async def mcp_delete(request: Request):
        _validate_protocol_header(request)
        session_id = (request.headers.get(SESSION_HEADER) or "").strip()
        if not session_id:
            raise HTTPException(status_code=400, detail=f"Missing {SESSION_HEADER} header.")
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="MCP session not found.")
        sessions.pop(session_id, None)
        return Response(status_code=204)

    return app
