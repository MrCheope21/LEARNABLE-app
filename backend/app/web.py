"""Serves the built web client (web/dist) on the same origin as the API, when WEB_DIST_DIR is set.

Production runs one container for both (docs/DEPLOYMENT.md §6): the browser talks to /api on the
origin it was loaded from, so no CORS is needed (docs/WEB_ARCHITECTURE.md). In development
WEB_DIST_DIR is unset and nothing here runs: Vite serves the client and proxies /api.

It hooks the router's fallback, which runs only when no route matched at all. Every API route
keeps its exact behaviour (a known path with the wrong method is still a 405), and an unknown
/api path is still the JSON 404, never the web page.
"""

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import Receive, Scope, Send

from app.core.config import get_settings

# Vite fingerprints everything under assets/ (name-hash.js), so those files never change.
_IMMUTABLE = "public, max-age=31536000, immutable"


def web_response(dist: Path, path: str) -> Response:
    """The file for `path` inside `dist`, or index.html so the client-side router can handle
    the URL (/courses/…, /reset-password?token=…). A missing fingerprinted asset is a 404: an
    HTML page served as JavaScript would only fail more confusingly."""
    root = dist.resolve()
    relative = path.lstrip("/")
    if relative:
        candidate = (root / relative).resolve()
        # resolve() + containment check: "/../x" or a symlink can't reach outside dist.
        if candidate.is_relative_to(root) and candidate.is_file():
            cache = _IMMUTABLE if relative.startswith("assets/") else "no-cache"
            return FileResponse(
                candidate, headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"}
            )
        if relative.startswith("assets/"):
            return PlainTextResponse("Not found", status_code=404)
    return FileResponse(
        root / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"}
    )


def install_web_app(app: FastAPI) -> None:
    fallback = app.router.default

    async def default(scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        dist = get_settings().web_dist_dir if scope["type"] == "http" else None
        if (
            dist is None
            or scope.get("method") not in ("GET", "HEAD")
            or path == "/api"
            or path.startswith("/api/")
        ):
            await fallback(scope, receive, send)
            return
        await web_response(dist, path)(scope, receive, send)

    app.router.default = default
