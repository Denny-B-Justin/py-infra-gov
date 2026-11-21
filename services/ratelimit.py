"""In-process sliding-window rate limiter (per key, e.g. IP or user id).

Account lockout is persisted in the database (failed_login_count /
locked_until), so it also holds across worker processes; this limiter adds a
cheap per-process throttle for brute force and abuse of costly endpoints.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(bucket: str, key: str, limit: int, window_sec: int) -> bool:
    now = time.monotonic()
    k = f"{bucket}:{key}"
    with _lock:
        q = _hits[k]
        while q and now - q[0] > window_sec:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 50_000:  # bound memory
            for stale in [x for x, v in _hits.items() if not v][:10_000]:
                _hits.pop(stale, None)
        return True


def reset(bucket: str, key: str) -> None:
    with _lock:
        _hits.pop(f"{bucket}:{key}", None)
