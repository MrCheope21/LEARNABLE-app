"""Security headers on every response.

The web app loads only its own files, so the Content-Security-Policy allows nothing else: an
injected script can't run and the page can't be framed. Inline styles stay allowed because React
`style` attributes need them. The microphone is allowed for dictation, on this origin only.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

_ALWAYS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    # Reset links carry their token in the URL: never send it to another site.
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"microphone=(self), camera=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
)
# FastAPI's interactive docs load their scripts from a CDN.
_DOCS = ("/docs", "/redoc")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        extra: list[tuple[bytes, bytes]] = list(_ALWAYS)
        if not path.startswith(_DOCS):
            extra.append((b"content-security-policy", CONTENT_SECURITY_POLICY.encode()))
        if scope.get("scheme") == "https":
            extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        if path.startswith("/api/"):
            # Account data must not stay in the browser's cache after sign-out.
            extra.append((b"cache-control", b"no-store"))

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers += [(name, value) for name, value in extra if name not in present]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
