"""滑动窗口请求限流（RainViewer：约 100 次/IP/分钟）。"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Optional


class SlidingWindowRateLimiter:
    """线程安全的滑动 60 秒窗口限流器。"""

    def __init__(self, max_per_minute: int = 80, window_seconds: float = 60.0):
        self.max_per_minute = max(1, int(max_per_minute))
        self.window_seconds = float(window_seconds)
        self._times: Deque[float] = deque()
        self._lock = threading.Lock()
        self._paused_until: float = 0.0
        self._last_429_at: Optional[float] = None
        self._total_requests: int = 0
        self._queued: int = 0

    def configure(self, max_per_minute: int) -> None:
        with self._lock:
            self.max_per_minute = max(1, int(max_per_minute))

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

    def status(self) -> Dict:
        now = time.time()
        with self._lock:
            self._prune(now)
            paused = max(0.0, self._paused_until - now)
            return {
                'window_count': len(self._times),
                'max_per_minute': self.max_per_minute,
                'paused_seconds': round(paused, 1),
                'rate_limited': paused > 0,
                'total_requests': self._total_requests,
                'queued': self._queued,
                'last_429_at': self._last_429_at,
            }

    def set_queued(self, n: int) -> None:
        with self._lock:
            self._queued = max(0, int(n))

    def note_429(self, backoff_seconds: float = 30.0) -> None:
        now = time.time()
        with self._lock:
            self._last_429_at = now
            self._paused_until = max(self._paused_until, now + backoff_seconds)

    def seconds_until_slots(self, count: int) -> float:
        """现在就能拿走 count 个名额时返回 0，否则返回需要等待的秒数。"""
        count = max(1, int(count))
        now = time.time()
        with self._lock:
            if now < self._paused_until:
                return max(0.0, self._paused_until - now)
            self._prune(now)
            free = self.max_per_minute - len(self._times)
            if free >= count:
                return 0.0
            need = count - free
            idx = need - 1
            if idx < 0 or idx >= len(self._times):
                return self.window_seconds
            return max(0.05, self._times[idx] + self.window_seconds - now + 0.05)

    def try_reserve(self, count: int) -> bool:
        """立刻占用 count 个名额。名额不够或处于暂停时不占用，返回 False。"""
        count = max(1, int(count))
        now = time.time()
        with self._lock:
            if now < self._paused_until:
                return False
            self._prune(now)
            if len(self._times) + count > self.max_per_minute:
                return False
            for _ in range(count):
                self._times.append(now)
                self._total_requests += 1
            return True

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        阻塞直到窗口有名额。timeout 秒后返回 False。
        """
        start = time.time()
        while True:
            now = time.time()
            with self._lock:
                if now < self._paused_until:
                    wait = self._paused_until - now
                else:
                    self._prune(now)
                    if len(self._times) < self.max_per_minute:
                        self._times.append(now)
                        self._total_requests += 1
                        return True
                    wait = self.window_seconds - (now - self._times[0]) + 0.05
            if timeout is not None and (time.time() - start + wait) > timeout:
                return False
            time.sleep(min(max(wait, 0.05), 2.0))


# 进程内单例，供管线与 API 状态共用
_global_limiter = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    return _global_limiter
