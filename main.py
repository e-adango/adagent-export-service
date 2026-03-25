from __future__ import annotations

import html
import os
from functools import lru_cache
from typing import Iterable, Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

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
    has_glb = False
    for export_format in formats:
        escaped_format = html.escape(export_format)
        href = html.escape(f"/{session_id}/{export_format}", quote=True)
        rows.append(
            "<a class=\"download-button\" "
            f"href=\"{href}\">Download {escaped_format.upper()}</a>"
        )
        if export_format == "glb":
            has_glb = True

    downloads_section = (
        "<div class=\"downloads-grid\">"
        f"{''.join(rows)}"
        "</div>"
        if rows
        else "<p class=\"empty-state\">No exports available yet for this session.</p>"
    )
    preview_section = "<p class=\"empty-state\">No preview available yet.</p>"
    if has_glb:
        glb_src = html.escape(f"/{session_id}/glb", quote=True)
        preview_section = (
            "<div class=\"preview-card\">"
            '<model-viewer style="width:100%;height:420px;border-radius:18px;" '
            f'src="{glb_src}" camera-controls auto-rotate></model-viewer>'
            "</div>"
            '<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>'
        )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>CADAgent exports for {escaped_session_id}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Sora:wght@400;500;700&display=swap" rel="stylesheet" />
    <style>
      :root {{
        --bg-1: #010c14;
        --bg-2: #02101d;
        --bg-glow: rgba(0, 202, 158, 0.14);
        --ink: #edf4ff;
        --ink-soft: #9cb2cc;
        --card: rgba(3, 20, 33, 0.7);
        --line: rgba(142, 173, 211, 0.24);
        --accent: #00d79d;
        --button-bg: linear-gradient(120deg, #12253a 0%, #0b1830 100%);
        --button-ink: #e9f4ff;
        --preview-bg: rgba(11, 22, 36, 0.84);
      }}
      :root[data-theme='light'] {{
        --bg-1: #e7f1ff;
        --bg-2: #f9fcff;
        --bg-glow: rgba(0, 142, 104, 0.16);
        --ink: #0e2338;
        --ink-soft: #3d5670;
        --card: rgba(255, 255, 255, 0.78);
        --line: rgba(24, 58, 93, 0.14);
        --accent: #008f68;
        --button-bg: linear-gradient(120deg, #f2f7ff 0%, #dbe8f6 100%);
        --button-ink: #0b2942;
        --preview-bg: rgba(237, 244, 252, 0.95);
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
        padding: 1.5rem 1.2rem 3rem;
      }}
      .shell {{
        max-width: 960px;
        margin: 0 auto;
      }}
      .theme-toggle {{
        border: 1px solid var(--line);
        background: var(--card);
        color: var(--ink);
        border-radius: 999px;
        padding: 0.5rem 0.9rem;
        font-size: 0.85rem;
        cursor: pointer;
        backdrop-filter: blur(10px);
      }}
      .topbar {{
        display: flex;
        justify-content: flex-end;
      }}
      .hero {{
        margin-top: 1.5rem;
        text-align: center;
        border: 1px solid var(--line);
        background: var(--card);
        border-radius: 26px;
        padding: clamp(1.6rem, 3vw, 2.4rem);
        backdrop-filter: blur(16px);
      }}
      .brand {{
        display: inline-flex;
        align-items: center;
        gap: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        font-size: clamp(1.2rem, 2.7vw, 2rem);
      }}
      .brand-mark {{
        width: 1.2em;
        height: 1.2em;
        border: 2px solid currentColor;
        border-radius: 0.18em;
        transform: rotate(45deg);
        opacity: 0.85;
      }}
      .status-pill {{
        margin: 1.2rem auto 1.4rem;
        display: inline-block;
        border-radius: 999px;
        border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
        background: color-mix(in srgb, var(--accent) 12%, transparent);
        color: var(--accent);
        font-size: 0.86rem;
        padding: 0.45rem 0.9rem;
        font-weight: 500;
      }}
      h1 {{
        margin: 0;
        line-height: 1.05;
        font-size: clamp(2rem, 6vw, 4.2rem);
      }}
      .subline {{
        margin: 0.35rem 0 0;
        font-family: 'Cormorant Garamond', serif;
        font-size: clamp(2rem, 5vw, 3.5rem);
        font-weight: 500;
        letter-spacing: 0.01em;
      }}
      .copy {{
        max-width: 700px;
        margin: 1rem auto 0;
        color: var(--ink-soft);
        line-height: 1.6;
      }}
      .session-chip {{
        margin-top: 1rem;
        display: inline-block;
        font-size: 0.78rem;
        color: var(--ink-soft);
        border: 1px dashed var(--line);
        border-radius: 999px;
        padding: 0.38rem 0.75rem;
      }}
      .downloads {{
        margin-top: 1.8rem;
      }}
      .downloads-grid {{
        display: grid;
        gap: 0.85rem;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }}
      .download-button {{
        text-decoration: none;
        display: inline-flex;
        justify-content: center;
        align-items: center;
        border-radius: 999px;
        padding: 0.9rem 1.1rem;
        border: 1px solid var(--line);
        background: var(--button-bg);
        color: var(--button-ink);
        font-weight: 600;
        box-shadow: 0 12px 28px rgba(3, 18, 32, 0.28);
      }}
      .section-title {{
        margin: 2rem 0 0.9rem;
        font-size: 1.1rem;
      }}
      .preview-card {{
        border-radius: 20px;
        border: 1px solid var(--line);
        background: var(--preview-bg);
        padding: 0.65rem;
      }}
      .empty-state {{
        color: var(--ink-soft);
      }}
      @media (max-width: 640px) {{
        .hero {{ border-radius: 20px; }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="topbar">
        <button id="theme-toggle" class="theme-toggle" type="button">Switch Theme</button>
      </div>
      <main class="hero">
        <div class="brand"><span class="brand-mark"></span><span>CADAgent</span></div>
        <div class="status-pill">Now Live</div>
        <h1>Intent-first engineering.</h1>
        <p class="subline">Express. Refine. Produce.</p>
        <p class="copy">
          A free, open source Fusion 360 add-in that turns your intent into editable CAD.
          Export and share this session in one place.
        </p>
        <div class="session-chip">Session {escaped_session_id}</div>
        <section class="downloads">
          <h2 class="section-title">Downloads</h2>
          {downloads_section}
        </section>
        <section>
          <h2 class="section-title">Preview</h2>
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
          button.textContent = theme === 'dark' ? 'Switch To Light' : 'Switch To Dark';
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
def download_export(session_id: str, export_format: str) -> RedirectResponse:
    return RedirectResponse(url=f"/{session_id}/{export_format}", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@app.get("/exports/{session_id}", response_class=HTMLResponse)
def list_exports(session_id: str) -> HTMLResponse:
    return RedirectResponse(url=f"/{session_id}", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@app.get("/{session_id}/{export_format}")
def download_export_canonical(session_id: str, export_format: str) -> StreamingResponse:
    return _download_export_response(session_id=session_id, export_format=export_format)


@app.get("/{session_id}", response_class=HTMLResponse)
def list_exports_canonical(session_id: str) -> HTMLResponse:
    try:
        formats = _list_formats(session_id)
    except ClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"S3 listing failed: {exc}") from exc

    return HTMLResponse(_render_page(session_id, formats))
