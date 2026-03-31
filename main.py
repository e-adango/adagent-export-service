from __future__ import annotations

import html
import os
from functools import lru_cache
from typing import Iterable, Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from cadagent_mcp.server import create_app as create_mcp_app

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


def _mcp_backend_url() -> str:
    return (
        str(
            os.environ.get("CADAGENT_BACKEND_URL")
            or os.environ.get("PARTSPEC_BACKEND_URL")
            or "http://13.60.23.36"
        )
        .strip()
        .rstrip("/")
    )



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
    has_glb = False
    for export_format in formats:
        escaped_format = html.escape(export_format)
        href = html.escape(f"/exports/{session_id}/{export_format}", quote=True)
        rows.append(
            "<a class=\"format-link\" "
            f"href=\"{href}\">{escaped_format.upper()}</a>"
        )
        if export_format == "glb":
            has_glb = True

    downloads_section = (
        "<nav class=\"formats\" aria-label=\"Available export formats\">"
        f"{''.join(rows)}"
        "</nav>"
        if rows
        else "<p class=\"empty-state\">No exports available yet for this session.</p>"
    )
    preview_section = "<p class=\"empty-state\">No preview available yet.</p>"
    if has_glb:
        glb_src = html.escape(f"/{session_id}/glb", quote=True)
        preview_section = (
            "<div class=\"preview\">"
            '<model-viewer style="width:100%;height:min(52vh,440px);" '
            f'src="{glb_src}" camera-controls auto-rotate></model-viewer>'
            "</div>"
            '<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>'
        )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CADAgent Session {escaped_session_id}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Sora:wght@400;500;700&display=swap" rel="stylesheet" />
    <style>
      :root {{
        --bg-1: #02080f;
        --bg-2: #031421;
        --bg-glow: rgba(0, 176, 123, 0.16);
        --ink: #f4f8ff;
        --ink-soft: #8fa4bc;
        --line: rgba(141, 170, 206, 0.35);
        --accent: #09d89c;
      }}
      :root[data-theme='light'] {{
        --bg-1: #f5fbff;
        --bg-2: #e9f3ff;
        --bg-glow: rgba(0, 123, 90, 0.12);
        --ink: #0c2136;
        --ink-soft: #50677f;
        --line: rgba(13, 52, 88, 0.22);
        --accent: #007a59;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; min-height: 100%; }}
      body {{
        font-family: 'Sora', 'Segoe UI', sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at 15% 15%, var(--bg-glow), transparent 45%),
          radial-gradient(circle at 85% 10%, rgba(38, 99, 180, 0.18), transparent 40%),
          linear-gradient(160deg, var(--bg-1) 0%, var(--bg-2) 100%);
        transition: background 180ms ease, color 180ms ease;
        padding: clamp(1rem, 2vw, 1.8rem);
      }}
      .page {{
        max-width: 840px;
        margin: 0 auto;
      }}
      .topbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.1rem 0;
        border-bottom: 1px solid var(--line);
      }}
      .brand {{
        display: inline-flex;
        align-items: baseline;
        gap: 0.18rem;
        color: var(--ink);
        text-decoration: none;
        font-weight: 700;
        letter-spacing: 0.01em;
      }}
      .brand em {{
        font-style: normal;
        font-weight: 400;
        opacity: 0.9;
      }}
      .theme-toggle {{
        border: 0;
        background: transparent;
        color: var(--ink-soft);
        padding: 0.25rem 0;
        font: inherit;
        font-size: 0.84rem;
        cursor: pointer;
      }}
      .theme-toggle:hover {{
        color: var(--ink);
      }}
      main {{
        padding-top: clamp(1.4rem, 5vw, 4rem);
      }}
      h1 {{
        margin: 0;
        line-height: 1.02;
        font-size: clamp(2rem, 6.6vw, 4.8rem);
        letter-spacing: -0.02em;
      }}
      .subline {{
        margin: 0.3rem 0 0;
        font-family: 'Cormorant Garamond', serif;
        font-size: clamp(1.9rem, 4.8vw, 3.6rem);
        font-weight: 500;
        letter-spacing: 0.01em;
      }}
      .meta {{
        margin: 0.9rem 0 0;
        color: var(--ink-soft);
        font-size: 0.86rem;
      }}
      .downloads {{
        margin-top: 1.4rem;
      }}
      .formats {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.95rem 1.25rem;
      }}
      .format-link {{
        color: var(--ink);
        text-decoration: none;
        font-weight: 600;
        letter-spacing: 0.05em;
        font-size: 0.84rem;
        padding-bottom: 0.18rem;
        border-bottom: 1px solid var(--line);
      }}
      .format-link:hover {{
        color: var(--accent);
        border-bottom-color: currentColor;
      }}
      .preview {{
        margin-top: 1.3rem;
        padding-top: 1.2rem;
        border-top: 1px solid var(--line);
      }}
      .empty-state {{
        color: var(--ink-soft);
        font-size: 0.9rem;
      }}
      @media (max-width: 640px) {{
        .formats {{
          gap: 0.65rem 1rem;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="page">
      <div class="topbar">
        <a class="brand" href="https://cadagent.co"><span>CAD</span><em>Agent</em></a>
        <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light and dark theme">
          Theme
        </button>
      </div>
      <main>
        <h1>Intent-first engineering.</h1>
        <p class="subline">Express. Refine. Produce.</p>
        <p class="meta">Session {escaped_session_id}</p>
        <section class="downloads">
          {downloads_section}
        </section>
        <section>
          {preview_section}
        </section>
      </main>
    </div>
    <script>
      (function() {{
        var root = document.documentElement;
        var key = 'cadagent-export-theme';
        var stored = localStorage.getItem(key);
        if (!stored) {{
          stored = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
        }}
        root.setAttribute('data-theme', stored);

        var button = document.getElementById('theme-toggle');
        function updateButton(theme) {{
          button.textContent = theme === 'dark' ? 'Light' : 'Dark';
        }}
        updateButton(stored);
        button.addEventListener('click', function() {{
          var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
          root.setAttribute('data-theme', next);
          localStorage.setItem(key, next);
          updateButton(next);
        }});
      }})();
    </script>
  </body>
</html>"""

@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'><title>CADAgent export service</title></head>"
        "<body><main><h1>CADAgent export service</h1><p>Service is running.</p></main></body></html>"
    )


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


def _download_export_response(session_id: str, export_format: str) -> StreamingResponse:
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


@app.get("/exports/{session_id}/{export_format}")
def download_export(session_id: str, export_format: str) -> StreamingResponse:
    return _download_export_response(session_id=session_id, export_format=export_format)


@app.get("/exports/{session_id}", response_class=HTMLResponse)
def list_exports(session_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/download-page?session_id={session_id}", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@app.get("/download-page", response_class=HTMLResponse)
def download_page(
    session_id: str = Query(default="", min_length=1),
) -> HTMLResponse:
    try:
        formats = _list_formats(session_id)
    except ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 listing failed: {exc}") from exc

    return HTMLResponse(_render_page(session_id, formats))


mcp_app = create_mcp_app(backend_base_url=_mcp_backend_url())
app.mount("/", mcp_app)
