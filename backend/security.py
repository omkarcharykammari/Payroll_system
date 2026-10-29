"""Security, token hashing, CSRF protection, and rate limiting helpers."""
import hashlib
import secrets
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

from fastapi import HTTPException, Request, status


# --------------------------------------------------------------------------- #
# Secure Token Generation & Hashing
# --------------------------------------------------------------------------- #
def generate_secure_token() -> str:
    """Generate a high-entropy URL-safe token (32 random bytes = ~43 chars)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a raw token with SHA-256 for secure database lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Simple In-Memory Sliding Window Rate Limiter
# --------------------------------------------------------------------------- #
class RateLimiter:
    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window_seconds = window_seconds
        self.records: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def check(self, key: str) -> bool:
        """Returns True if allowed, False if limit exceeded."""
        now = time.time()
        with self.lock:
            timestamps = self.records[key]
            # Prune older than window
            cutoff = now - self.window_seconds
            self.records[key] = [t for t in timestamps if t > cutoff]
            if len(self.records[key]) >= self.requests:
                return False
            self.records[key].append(now)
            return True

    def retry_after(self, key: str) -> int:
        now = time.time()
        with self.lock:
            timestamps = self.records.get(key, [])
            if not timestamps:
                return 1
            earliest = timestamps[0]
            remaining = int((earliest + self.window_seconds) - now)
            return max(1, remaining)


import os

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")

# 5 attempts per minute for login and password reset
login_limiter = RateLimiter(requests=5, window_seconds=60)
# 10 attempts per minute for invite acceptance & company creation
invite_limiter = RateLimiter(requests=10, window_seconds=60)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def enforce_rate_limit(request: Request, limiter: RateLimiter, prefix: str = ""):
    if not RATE_LIMIT_ENABLED or os.getenv("TESTING") == "1":
        return
    client_ip = get_client_ip(request)
    key = f"{prefix}:{client_ip}"
    if not limiter.check(key):
        retry_after = limiter.retry_after(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
