"""HTTP client for backend MCP runtime APIs."""

from __future__ import annotations

import ast
import json
from typing import Any, Dict, Optional

import httpx


class BackendClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def create_session(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/mcp/sessions", arguments)

    async def write_spec(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "session_id": arguments.get("session_id"),
            "part_spec": arguments.get("part_spec"),
        }
        if "allow_large_regen" in arguments:
            payload["allow_large_regen"] = _coerce_bool_argument(
                arguments.get("allow_large_regen"),
                field_name="allow_large_regen",
            )
        return await self._post("/mcp/authoring", payload)

    async def undo_write_spec(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/mcp/authoring/undo", arguments)

    async def export(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/mcp/exports", arguments)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", path, payload=payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(method=method, url=url, json=payload)

        if response.status_code >= 400:
            detail = ""
            try:
                parsed = response.json()
                detail_value = parsed.get("detail") if isinstance(parsed, dict) else parsed
                if isinstance(detail_value, dict):
                    if "error" in detail_value and isinstance(detail_value.get("error"), dict):
                        detail = json.dumps({"error": detail_value["error"]}, separators=(",", ":"))
                    else:
                        detail = json.dumps(detail_value, separators=(",", ":"))
                else:
                    detail = str(detail_value or parsed)
            except Exception:
                detail = response.text
            if response.status_code == 404 and path.startswith("/mcp/"):
                detail = await _augment_missing_mcp_route_detail_for_client(self, detail)
            raise BackendMCPError(
                status_code=int(response.status_code),
                path=path,
                detail=detail,
                category=_classify_backend_failure(path=path, status_code=int(response.status_code), detail=detail),
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Backend MCP request returned invalid JSON for {path}.") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Backend MCP response was not an object for {path}.")
        return data


class BackendMCPError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        path: str,
        detail: Optional[str] = None,
        category: Optional[str] = None,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        request_id: Optional[str] = None,
        recovery_hint: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = int(status_code)
        self.path = str(path)
        self.detail = str(detail or "").strip()
        self.category = str(category or "backend_error")
        extracted_backend_error = _extract_backend_error_payload(self.detail)
        extracted_message = str(extracted_backend_error.get("message") or "").strip() if extracted_backend_error else ""
        extracted_code = str(extracted_backend_error.get("code") or "").strip() if extracted_backend_error else ""
        extracted_request_id = (
            str(extracted_backend_error.get("request_id") or "").strip() if extracted_backend_error else ""
        )
        extracted_recovery_hint = (
            str(extracted_backend_error.get("recovery_hint") or "").strip() if extracted_backend_error else ""
        )

        self.error_code = str(error_code or extracted_code or "BACKEND_HTTP_ERROR").strip()
        self.message = str(message or extracted_message or self.detail or "Backend MCP request failed.").strip()
        self.request_id = str(request_id or extracted_request_id or "").strip() or None
        self.recovery_hint = str(recovery_hint or extracted_recovery_hint or "").strip() or None
        self.payload = dict(payload or {})

        super().__init__(f"Backend MCP request failed ({self.status_code}) for {self.path}: {self.message}")

    def to_jsonrpc_data(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "source": "cadagent-backend",
            "status_code": self.status_code,
            "http_status": self.status_code,
            "path": self.path,
            "category": self.category,
            "detail": self.detail,
            "code": self.error_code,
            "message": self.message,
        }
        if self.request_id:
            payload["request_id"] = self.request_id
        if self.recovery_hint:
            payload["recovery_hint"] = self.recovery_hint
        if self.payload:
            payload["payload"] = dict(self.payload)
        backend_error = _extract_backend_error_payload(self.detail)
        if backend_error:
            payload["backend_error"] = backend_error
            payload["code"] = str(backend_error.get("code") or payload["code"])
            payload["message"] = str(backend_error.get("message") or payload["message"])
            if not payload.get("request_id") and backend_error.get("request_id"):
                payload["request_id"] = str(backend_error["request_id"])
            if not payload.get("recovery_hint") and backend_error.get("recovery_hint"):
                payload["recovery_hint"] = str(backend_error["recovery_hint"])
        return payload

    def to_error_data(self) -> Dict[str, Any]:
        return self.to_jsonrpc_data()


def backend_error_to_tool_result(
    exc: BackendMCPError,
    *,
    fallback_request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Map backend transport errors into MCP tool-level errors."""

    error_data = exc.to_jsonrpc_data()
    request_id = str(error_data.get("request_id") or fallback_request_id or "").strip() or None
    recovery_hint = str(error_data.get("recovery_hint") or "").strip() or None

    error_payload: Dict[str, Any] = {
        "source": "cadagent-backend",
        "code": str(error_data.get("code") or exc.error_code or "BACKEND_HTTP_ERROR").strip() or "BACKEND_HTTP_ERROR",
        "message": str(error_data.get("message") or exc.message or "Backend MCP request failed.").strip()
        or "Backend MCP request failed.",
        "category": str(error_data.get("category") or exc.category or "backend_error").strip() or "backend_error",
        "status_code": int(error_data.get("status_code") or exc.status_code),
        "path": str(error_data.get("path") or exc.path).strip(),
    }
    if request_id:
        error_payload["request_id"] = request_id
    if recovery_hint:
        error_payload["recovery_hint"] = recovery_hint

    backend_error = error_data.get("backend_error")
    if isinstance(backend_error, dict) and backend_error:
        error_payload["backend_error"] = backend_error
        if "details" in backend_error:
            error_payload["details"] = backend_error["details"]

    return {"isError": True, "error": error_payload}


def backend_error_to_tool_text(tool_name: str, tool_result: Dict[str, Any]) -> str:
    error = tool_result.get("error")
    if not isinstance(error, dict):
        return f"{tool_name} failed."
    code = str(error.get("code") or "BACKEND_HTTP_ERROR").strip() or "BACKEND_HTTP_ERROR"
    message = str(error.get("message") or "Backend MCP request failed.").strip() or "Backend MCP request failed."
    recovery_hint = str(error.get("recovery_hint") or "").strip()
    base = f"{tool_name} failed ({code}): {message}"
    return f"{base} Recovery: {recovery_hint}" if recovery_hint else base


def _classify_backend_failure(*, path: str, status_code: int, detail: str) -> str:
    lowered = str(detail or "").lower()

    if status_code == 404 and "/mcp/" in path:
        return "missing_mcp_route"
    if status_code == 404 and "session" in lowered:
        return "session_not_found"
    if status_code == 409 and "stale" in lowered:
        return "stale_reference"
    if status_code == 422:
        return "schema_validation"
    if status_code >= 500:
        return "backend_internal_error"
    if status_code in (401, 403):
        return "auth_error"
    if "no build123d part" in lowered or "without producing a solid" in lowered:
        return "no_geometry"
    return "backend_error"


async def _augment_missing_mcp_route_detail_for_client(client: BackendClient, original_detail: str) -> str:
    diagnostic_parts = [str(original_detail or "").strip()]
    backend_has_mcp_routes = await _backend_has_mcp_routes(client)
    if backend_has_mcp_routes is False:
        diagnostic_parts.append(
            f"Backend at {client.base_url} does not expose MCP runtime routes like /mcp/sessions."
        )
    diagnostic_parts.append(
        "Set CADAGENT_BACKEND_URL to a CADAgent backend build that includes MCP endpoints."
    )
    return " ".join(part for part in diagnostic_parts if part)


async def _backend_has_mcp_routes(client: BackendClient) -> Optional[bool]:
    openapi_url = f"{client.base_url}/openapi.json"
    try:
        async with httpx.AsyncClient(timeout=client.timeout_seconds) as request_client:
            response = await request_client.get(openapi_url)
    except Exception:
        return None

    if response.status_code >= 400:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    paths = data.get("paths")
    if not isinstance(paths, dict):
        return None
    return "/mcp/sessions" in paths


def _extract_backend_error_payload(detail: str) -> Optional[Dict[str, Any]]:
    text = str(detail or "").strip()
    if not text:
        return None

    parsed: Optional[Any] = None
    try:
        parsed = json_parse_safe(text)
    except Exception:
        parsed = None
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        return None
    error = parsed.get("error")
    if isinstance(error, dict):
        return error
    return None


def json_parse_safe(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return ast.literal_eval(text)
    except Exception:
        return None


def _coerce_bool_argument(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"{field_name} must be a boolean or 0/1 when provided as an integer.")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"{field_name} must be a boolean-like string when provided as text.")
    raise ValueError(f"{field_name} must be a boolean.")
