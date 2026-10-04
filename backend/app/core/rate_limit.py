"""Per-IP and per-account attempt limits for sign-in, sign-up, password and AI-heavy endpoints.

Sliding windows kept in this process's memory: enough for one server (the documented
deployments run one), reset on restart. Behind several replicas they would need a shared store
such as Redis. The client IP is the one uvicorn derives from the proxy's X-Forwarded-For, which is
trustworthy only because the backend port is not exposed directly (docker-compose.yml).
"""

import time
from collections import deque
from collections.abc import Callable
from threading import Lock

from fastapi import Depends, Request

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.errors import RateLimitedError
from app.models.user import User

# Keys idle for a full window are dropped when the table grows past this.
_MAX_KEYS = 50_000


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _window(self, key: str, window: float, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits

    def retry_after(self, key: str, limit: int, window: float) -> float | None:
        """Seconds until `key` may try again, or None if it is under the limit. Records nothing."""
        now = time.monotonic()
        with self._lock:
            hits = self._window(key, window, now)
            return hits[0] + window - now if len(hits) >= limit else None

    def record(self, key: str, window: float) -> None:
        now = time.monotonic()
        with self._lock:
            self._window(key, window, now).append(now)
            if len(self._hits) > _MAX_KEYS:
                for stale in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
                    del self._hits[stale]

    def hit_check(self, key: str, limit: int, window: float) -> None:
        """Raises RateLimitedError (429) if `key` is over the limit, without counting."""
        if not get_settings().rate_limits_enabled:
            return
        wait = self.retry_after(key, limit, window)
        if wait is not None:
            raise RateLimitedError(wait)

    def hit(self, key: str, limit: int, window: float) -> None:
        """Counts one attempt, raising RateLimitedError (429) when over the limit."""
        self.hit_check(key, limit, window)
        if get_settings().rate_limits_enabled:
            self.record(key, window)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def per_ip(name: str, limit: int, window: float) -> Callable[[Request], None]:
    """A route dependency: at most `limit` requests per `window` seconds from one IP."""

    def dependency(request: Request) -> None:
        limiter.hit(f"{name}:ip:{client_ip(request)}", limit, window)

    return dependency


def per_user(name: str, limit: int, window: float) -> Callable[..., None]:
    """A route dependency: at most `limit` requests per `window` seconds for one account."""

    def dependency(user: User = Depends(get_current_user)) -> None:
        limiter.hit(f"{name}:user:{user.id}", limit, window)

    return dependency
