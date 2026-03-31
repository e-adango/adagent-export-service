"""stdio MCP transport for CADAgent."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional, TextIO
from uuid import uuid4

from .backend_client import (
    BackendClient,
    BackendMCPError,
    backend_error_to_tool_result,
    backend_error_to_tool_text,
)
from .guidance_registry import SERVER_INSTRUCTIONS, list_resources, read_resource
from .server import SUPPORTED_PROTOCOL_VERSION, _jsonrpc_error, _jsonrpc_result, _spatial_digest
from .tool_registry import TOOL_DEFINITIONS, call_tool

SERVER_INFO = {"name": "cadagent-mcp", "version": "0.2.0"}
STDIO_USER_AGENT = "cadagent-mcp-stdio/0.2.0"


def _new_request_id() -> str:
    return f"mcp_{uuid4().hex}"


def _protocol_error(
    request_id: Any,
    *,
    rpc_code: int,
    rpc_message: str,
    error_code: str,
    detail_message: str,
    trace_request_id: str,
    recovery_hint: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "code": error_code,
        "message": detail_message,
        "request_id": trace_request_id,
    }
    if recovery_hint:
        data["recovery_hint"] = recovery_hint
    if extra:
        data.update(extra)
    return _jsonrpc_error(request_id, rpc_code, rpc_message, data=data)


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


class StdioTransportServer:
    """Minimal stdio MCP runtime for Claude Desktop and local integrations."""

    def __init__(self, backend_base_url: Optional[str] = None) -> None:
        self.backend_url = (
            backend_base_url or os.environ.get("CADAGENT_BACKEND_URL") or "http://localhost:8000"
        ).rstrip("/")
        self.backend_client = BackendClient(self.backend_url)
        self._initialized = False

    async def handle_payload(self, payload: Any) -> Optional[Any]:
        if isinstance(payload, dict):
            return await self._handle_item(payload)

        if not isinstance(payload, list):
            return _protocol_error(
                None,
                rpc_code=-32600,
                rpc_message="Invalid Request",
                error_code="INVALID_REQUEST",
                detail_message="stdin payload must be a JSON-RPC object or batch array.",
                trace_request_id=_new_request_id(),
            )

        if not payload:
            return _protocol_error(
                None,
                rpc_code=-32600,
                rpc_message="Invalid Request",
                error_code="INVALID_REQUEST",
                detail_message="Batch requests must contain at least one item.",
                trace_request_id=_new_request_id(),
            )

        responses = []
        for item in payload:
            response = await self._handle_item(item)
            if response is not None:
                responses.append(response)
        return responses or None

    async def _handle_item(self, item: Any) -> Optional[Dict[str, Any]]:
        trace_request_id = _new_request_id()
        if not isinstance(item, dict):
            return _protocol_error(
                None,
                rpc_code=-32600,
                rpc_message="Invalid Request",
                error_code="INVALID_REQUEST",
                detail_message="Batch items must be JSON-RPC objects.",
                trace_request_id=trace_request_id,
            )

        request_id = item.get("id")
        if item.get("jsonrpc") != "2.0":
            return _protocol_error(
                request_id,
                rpc_code=-32600,
                rpc_message="Invalid Request",
                error_code="INVALID_REQUEST",
                detail_message="jsonrpc must be '2.0'.",
                trace_request_id=trace_request_id,
            )

        method = item.get("method")
        if not isinstance(method, str) or not method.strip():
            return _protocol_error(
                request_id,
                rpc_code=-32600,
                rpc_message="Invalid Request",
                error_code="INVALID_REQUEST",
                detail_message="method must be a non-empty string.",
                trace_request_id=trace_request_id,
            )

        method_name = method.strip()
        is_notification = "id" not in item or request_id is None

        if method_name == "initialize":
            if is_notification:
                return _protocol_error(
                    request_id,
                    rpc_code=-32600,
                    rpc_message="Invalid Request",
                    error_code="INVALID_REQUEST",
                    detail_message="initialize must be sent as a request with an id.",
                    trace_request_id=trace_request_id,
                )

            raw_params = item.get("params")
            if raw_params is not None and not isinstance(raw_params, dict):
                return _protocol_error(
                    request_id,
                    rpc_code=-32602,
                    rpc_message="Invalid params",
                    error_code="INVALID_INPUT",
                    detail_message="initialize params must be a JSON object when provided.",
                    trace_request_id=trace_request_id,
                )

            self._initialized = True
            return _jsonrpc_result(
                request_id,
                {
                    "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {}, "resources": {"listChanged": False}},
                    "instructions": SERVER_INSTRUCTIONS,
                },
            )

        if method_name == "ping":
            if is_notification:
                return None
            return _jsonrpc_result(request_id, {"pong": True})

        if method_name == "notifications/initialized":
            return None

        if is_notification:
            return None

        if not self._initialized:
            return _protocol_error(
                request_id,
                rpc_code=-32002,
                rpc_message="Server not initialized",
                error_code="MCP_NOT_INITIALIZED",
                detail_message="Send initialize before invoking CADAgent MCP tools.",
                trace_request_id=trace_request_id,
                recovery_hint="Send initialize, wait for the response, then send notifications/initialized.",
            )

        if method_name == "tools/list":
            return _jsonrpc_result(request_id, {"tools": TOOL_DEFINITIONS})

        if method_name == "resources/list":
            return _jsonrpc_result(request_id, {"resources": list_resources()})

        if method_name == "resources/read":
            raw_params = item.get("params")
            params = raw_params if isinstance(raw_params, dict) else {}
            resource_uri = str(params.get("uri") or "").strip()
            if not resource_uri:
                return _protocol_error(
                    request_id,
                    rpc_code=-32602,
                    rpc_message="Invalid params",
                    error_code="INVALID_INPUT",
                    detail_message="Missing resource uri.",
                    trace_request_id=trace_request_id,
                )
            try:
                return _jsonrpc_result(request_id, read_resource(resource_uri))
            except KeyError:
                return _jsonrpc_error(
                    request_id,
                    -32002,
                    "Resource not found",
                    data={"uri": resource_uri},
                )

        if method_name != "tools/call":
            return _protocol_error(
                request_id,
                rpc_code=-32601,
                rpc_message="Method not found",
                error_code="METHOD_NOT_FOUND",
                detail_message=f"Unknown method '{method_name}'.",
                trace_request_id=trace_request_id,
            )

        raw_params = item.get("params")
        if raw_params is None:
            params: Dict[str, Any] = {}
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            return _protocol_error(
                request_id,
                rpc_code=-32602,
                rpc_message="Invalid params",
                error_code="INVALID_INPUT",
                detail_message="params must be a JSON object when provided.",
                trace_request_id=trace_request_id,
            )

        tool_name = str(params.get("name") or "").strip()
        raw_arguments = params.get("arguments")
        if raw_arguments is None:
            arguments: Dict[str, Any] = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            return _protocol_error(
                request_id,
                rpc_code=-32602,
                rpc_message="Invalid params",
                error_code="INVALID_INPUT",
                detail_message="tool arguments must be a JSON object when provided.",
                trace_request_id=trace_request_id,
            )

        if not tool_name:
            return _protocol_error(
                request_id,
                rpc_code=-32602,
                rpc_message="Invalid params",
                error_code="INVALID_INPUT",
                detail_message="Tool name must be a non-empty string.",
                trace_request_id=trace_request_id,
            )

        try:
            result = await call_tool(tool_name, arguments, self.backend_client)
        except KeyError:
            return _protocol_error(
                request_id,
                rpc_code=-32601,
                rpc_message="Method not found",
                error_code="METHOD_NOT_FOUND",
                detail_message=f"Unknown tool '{tool_name}'.",
                trace_request_id=trace_request_id,
            )
        except BackendMCPError as exc:
            tool_error = backend_error_to_tool_result(exc, fallback_request_id=trace_request_id)
            return _jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": backend_error_to_tool_text(tool_name, tool_error)}],
                    "structuredContent": tool_error,
                    "isError": True,
                },
            )
        except Exception as exc:
            return _jsonrpc_result(
                request_id,
                _internal_tool_error_result(
                    tool_name,
                    detail=str(exc),
                    request_id=trace_request_id,
                ),
            )

        return _jsonrpc_result(
            request_id,
            {
                "content": [{"type": "text", "text": _summary_text(tool_name, result)}],
                "structuredContent": result,
            },
        )


def run_stdio_server(
    backend_base_url: Optional[str] = None,
    *,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
) -> None:
    """Serve newline-delimited MCP JSON-RPC messages over stdin/stdout."""

    server = StdioTransportServer(backend_base_url)

    while True:
        raw_line = input_stream.readline()
        if raw_line == "":
            return

        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            response: Optional[Any] = _protocol_error(
                None,
                rpc_code=-32700,
                rpc_message="Parse error",
                error_code="PARSE_ERROR",
                detail_message=f"Invalid JSON message: {exc.msg}.",
                trace_request_id=_new_request_id(),
            )
        else:
            try:
                response = asyncio.run(server.handle_payload(payload))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"cadagent-mcp stdio failure: {exc}", file=error_stream)
                response = _protocol_error(
                    None,
                    rpc_code=-32603,
                    rpc_message="Internal error",
                    error_code="INTERNAL_ERROR",
                    detail_message=str(exc),
                    trace_request_id=_new_request_id(),
                )

        if response is None:
            continue

        try:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()
        except BrokenPipeError:
            return


def run_stdio(backend_base_url: Optional[str] = None) -> None:
    run_stdio_server(backend_base_url)


__all__ = ["StdioTransportServer", "run_stdio", "run_stdio_server", "SUPPORTED_PROTOCOL_VERSION"]
