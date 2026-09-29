"""Low-overhead fuzzing statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time


@dataclass
class Statistics:
    executions: int = 0
    timeouts: int = 0
    crashes: int = 0
    interesting: int = 0
    minimized: int = 0
    started_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, *, timeout=False, crash=False, interesting=False,
                minimized=False):
        with self._lock:
            self.executions += 1
            self.timeouts += int(timeout)
            self.crashes += int(crash)
            self.interesting += int(interesting)
            self.minimized += int(minimized)

    def snapshot(self):
        with self._lock:
            elapsed = max(0.001, time.monotonic() - self.started_at)
            return {
                "executions": self.executions,
                "timeouts": self.timeouts,
                "crashes": self.crashes,
                "interesting": self.interesting,
                "minimized": self.minimized,
                "exec_per_sec": round(self.executions / elapsed, 2),
                "uptime_sec": round(elapsed, 1),
            }
