"""In-memory rate limiter for AI feature endpoints."""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status

# 20 requests per minute per IP
RATE_LIMIT_MAX_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

_ip_request_history: Dict[str, List[float]] = defaultdict(list)


def check_ai_rate_limit(request: Request) -> None:
    """Enforce maximum request threshold per client IP within a rolling time window."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS

    # Filter out requests older than the rolling window
    timestamps = [t for t in _ip_request_history[client_ip] if t > cutoff]
    _ip_request_history[client_ip] = timestamps

    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: Maximum {RATE_LIMIT_MAX_REQUESTS} AI requests per minute. Please try again shortly.",
        )

    _ip_request_history[client_ip].append(now)


def reset_rate_limits() -> None:
    """Reset rate limiter state (useful for tests or diagnostics)."""
    _ip_request_history.clear()
