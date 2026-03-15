from __future__ import annotations

import html
import os
from functools import lru_cache
from typing import Iterable, Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

SUPPORTED_FORMATS = {
    "step": "application/step",
    "stl": "model/stl",
    "glb": "model/gltf-binary",
}
BUCKET_ENV_NAMES = ("EXPORTS_BUCKET_NAME", "EXPORT_S3_BUCKET", "S3_BUCKET_NAME", "AWS_S3_BUCKET")
REGION_ENV_NAMES = ("AWS_REGION", "AWS_DEFAULT_REGION")
ENDPOINT_ENV_NAMES = ("AWS_ENDPOINT_URL", "S3_ENDPOINT_URL")

app = FastAPI(title="cadagent-export-service")


class ConfigError(RuntimeError):
    pass



def _get_env(*names: str, required: bool = False) -> str:
    for name in names:
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    if required:
        joined = ", ".join(names)
        raise ConfigError(f"Missing required environment variable. Set one of: {joined}")
    return ""



def _normalize_format(export_format: str) -> str:
    normalized = str(export_format or "").strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unsupported export format: {export_format}",
        )
    return normalized


@lru_cache(maxsize=1)
def _bucket_name() -> str:
    return _get_env(*BUCKET_ENV_NAMES, required=True)


@lru_cache(maxsize=1)
def _upload_secret() -> str:
    return _get_env("EXPORT_UPLOAD_SECRET", required=True)


@lru_cache(maxsize=1)
def _s3_client():
    region_name = _get_env(*REGION_ENV_NAMES)
    endpoint_url = _get_env(*ENDPOINT_ENV_NAMES)
    kwargs = {}
    if region_name:
        kwargs["region_name"] = region_name
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)



def _object_key(session_id: str, export_format: str) -> str:
    return f"exports/{session_id}/{export_format}"



def _list_formats(session_id: str) -> list[str]:
    prefix = f"exports/{session_id}/"
    formats: set[str] = set()
    continuation_token = None

    while True:
        kwargs = {"Bucket": _bucket_name(), "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = _s3_client().list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            key = str(item.get("Key") or "")
            if not key.startswith(prefix):
                continue
            export_format = key[len(prefix) :]
            if export_format in SUPPORTED_FORMATS:
                formats.add(export_format)
        if not response.get("IsTruncated"):
            return sorted(formats)
        continuation_token = response.get("NextContinuationToken")



def _render_page(session_id: str, formats: Iterable[str]) -> str:
    escaped_session_id = html.escape(session_id)
    rows = []
    for export_format in formats:
        escaped_format = html.escape(export_format)
        href = html.escape(f"/exports/{session_id}/{export_format}", quote=True)
        rows.append(f'<li><a href="{href}">{escaped_format.upper()}</a></li>')

    content = "\n".join(rows) if rows else "<li>No exports available yet.</li>"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CADAgent exports for {escaped_session_id}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; color: #111827; }}
      main {{ max-width: 48rem; margin: 0 auto; }}
      a {{ color: #2563eb; }}
    </style>
  </head>
  <body>
    <main>
      <h1>CADAgent exports</h1>
      <p>Session: <strong>{escaped_session_id}</strong></p>
      <ul>{content}</ul>
    </main>
  </body>
</html>"""



def _configure_bucket_lifecycle() -> None:
    _s3_client().put_bucket_lifecycle_configuration(
        Bucket=_bucket_name(),
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "cadagent-export-expiry",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "exports/"},
                    "Expiration": {"Days": 1},
                }
            ]
        },
    )


@app.on_event("startup")
def _startup() -> None:
    try:
        _configure_bucket_lifecycle()
    except ConfigError:
        raise
    except ClientError as exc:
        raise RuntimeError(f"Unable to configure S3 lifecycle policy: {exc}") from exc


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/exports/{session_id}/{export_format}")
async def upload_export(
    session_id: str,
    export_format: str,
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Response:
    expected_token = _upload_secret()
    if authorization != f"Bearer {expected_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    normalized_format = _normalize_format(export_format)
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request body must contain export bytes.")

    try:
        _s3_client().put_object(
            Bucket=_bucket_name(),
            Key=_object_key(session_id, normalized_format),
            Body=payload,
            ContentType=SUPPORTED_FORMATS[normalized_format],
        )
    except ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 upload failed: {exc}") from exc

    return Response(status_code=status.HTTP_201_CREATED)


@app.get("/exports/{session_id}/{export_format}")
def download_export(session_id: str, export_format: str) -> StreamingResponse:
    normalized_format = _normalize_format(export_format)

    try:
        response = _s3_client().get_object(Bucket=_bucket_name(), Key=_object_key(session_id, normalized_format))
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code") or "")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.") from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 download failed: {exc}") from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{session_id}.{normalized_format}"',
    }
    content_length = response.get("ContentLength")
    if content_length is not None:
        headers["Content-Length"] = str(content_length)

    return StreamingResponse(response["Body"].iter_chunks(), media_type=SUPPORTED_FORMATS[normalized_format], headers=headers)


@app.get("/exports/{session_id}", response_class=HTMLResponse)
def list_exports(session_id: str) -> HTMLResponse:
    try:
        formats = _list_formats(session_id)
    except ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 listing failed: {exc}") from exc

    return HTMLResponse(_render_page(session_id, formats))
