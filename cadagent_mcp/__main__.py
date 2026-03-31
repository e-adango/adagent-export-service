"""Entrypoint for running the CADAgent MCP server package."""

from __future__ import annotations

import argparse
import os

import uvicorn

from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="CADAgent MCP server")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default="http",
        help="Transport: 'http' starts a uvicorn HTTP server (default), 'stdio' uses stdin/stdout for Claude Desktop.",
    )
    args = parser.parse_args()

    backend_url = os.environ.get("CADAGENT_BACKEND_URL", "http://localhost:8000")

    if args.transport == "stdio":
        from .stdio_transport import run_stdio
        run_stdio(backend_url)
    else:
        app = create_app(backend_base_url=backend_url)
        host = os.environ.get("CADAGENT_MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("CADAGENT_MCP_PORT", "8080"))
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
