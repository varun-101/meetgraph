"""In-process sliding-window rate limiter (P5). Single-process MVP — swap for
Redis-backed limiting if the API ever scales horizontally.

Applied as pure ASGI-agnostic FastAPI middleware: rules match path prefixes;
key = client IP (+ path class). 429 with Retry-After on breach.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

# (path-prefix, method or None=any, max requests, window seconds)
RULES: list[tuple[str, str | None, int, int]] = [
    ("/auth/jwt/login", "POST", 5, 60),      # credential stuffing
    ("/auth/register", "POST", 3, 60),
    ("/memory/search", "POST", 20, 60),      # LLM spend
    ("/memory/brief", "GET", 20, 60),
    ("/memory/reingest", "POST", 4, 60),
    ("/memory/project", "DELETE", 4, 60),
    ("/webhooks/livekit", None, 120, 60),    # generous; signature-verified anyway
]
# presenter start is expensive (LLM + chromium)
RULES.append(("/meetings", "POST", 30, 60))

_hits: dict[str, deque[float]] = defaultdict(deque)
_LAST_SWEEP = [0.0]


def _match(path: str, method: str) -> tuple[str, int, int] | None:
    for prefix, rule_method, limit, window in RULES:
        if path.startswith(prefix) and (rule_method is None or rule_method == method):
            return prefix, limit, window
    return None


def check(ip: str, path: str, method: str) -> float | None:
    """Returns None if allowed, else seconds to wait (Retry-After)."""
    rule = _match(path, method)
    if rule is None:
        return None
    prefix, limit, window = rule
    now = time.monotonic()
    key = f"{ip}|{method}|{prefix}"
    q = _hits[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return max(0.0, q[0] + window - now)
    q.append(now)

    # occasional sweep so idle keys don't accumulate forever
    if now - _LAST_SWEEP[0] > 300:
        _LAST_SWEEP[0] = now
        for k in [k for k, v in _hits.items() if not v or v[-1] <= now - 600]:
            _hits.pop(k, None)
    return None


async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    wait = check(ip, request.url.path, request.method)
    if wait is not None:
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded"},
            headers={"Retry-After": str(int(wait) + 1)},
        )
    return await call_next(request)
