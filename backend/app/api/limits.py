"""Reject oversized request bodies before they're read.

The upload handler also enforces the limit, but only after the multipart body has been parsed
(and spooled to disk). Checking Content-Length first stops a multi-gigabyte upload from being
accepted at all. Requests without Content-Length (chunked) still hit the handler's check; a
reverse proxy in production should cap body size too.
"""

from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_response

# Multipart framing (boundaries, part headers) around the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, limit_bytes: Callable[[], int]) -> None:
        self.app = app
        self.limit_bytes = limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            for name, value in scope["headers"]:
                if name == b"content-length" and value.isdigit():
                    if int(value) > self.limit_bytes():
                        response = error_response(
                            413, "payload_too_large", "The request body is too large."
                        )
                        await response(scope, receive, send)
                        return
                    break
        await self.app(scope, receive, send)
