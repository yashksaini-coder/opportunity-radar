"""API hardening: per-client rate limiting and security headers.

The limiter is a sliding-window counter per (client IP, bucket) held
in process memory — no external dependency, which is right-sized for
a single-instance FastAPI app. If someone floods the API (or grabs a
deployed URL and scripts against it), they get 429s with Retry-After
instead of exhausting the process or the Bright Data account.

Behind a reverse proxy, start uvicorn with --proxy-headers (and a
trusted proxy) so request.client reflects the real client IP.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# route-class → (max requests, per window seconds)
DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "api": (120, 60),    # read endpoints: 120/min per IP
    "run": (3, 60),      # pipeline trigger: 3/min per IP
    "mutate": (10, 60),  # config mutations (add source): 10/min per IP
    "page": (60, 60),    # static page loads
}

_MAX_TRACKED_CLIENTS = 10_000  # hard memory cap under address-spoof floods


class SlidingWindowLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, limits: dict[str, tuple[int, int]] | None = None):
        self._limits = limits or DEFAULT_LIMITS
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, client: str, bucket: str, now: float | None = None) -> float:
        """Record a hit; return 0.0 if allowed, else seconds to wait."""
        limit, window = self._limits.get(bucket, self._limits["api"])
        now = time.monotonic() if now is None else now
        key = (client, bucket)
        with self._lock:
            if len(self._hits) > _MAX_TRACKED_CLIENTS:
                self._hits.clear()  # fail open rather than OOM
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.1, hits[0] + window - now)
            hits.append(now)
            return 0.0


def _bucket_for(request: Request) -> str:
    path = request.url.path
    if path == "/api/run" and request.method == "POST":
        return "run"
    if path == "/api/sources" and request.method == "POST":
        return "mutate"
    if path.startswith("/api/"):
        return "api"
    return "page"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: SlidingWindowLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or SlidingWindowLimiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        client = request.client.host if request.client else "unknown"
        retry_after = self.limiter.check(client, _bucket_for(request))
        if retry_after > 0:
            return JSONResponse(
                {"detail": "rate limit exceeded, slow down"},
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline browser-side protections for every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
