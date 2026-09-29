"""Advanced feedback helpers for V8-Fuzzer v2.3.0.

Tiny dependency-free helpers for heuristic corpus retention, crash deduplication,
and timeout artifact management. They are intentionally independent from d8.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


class FeatureFeedback:
    """Retain inputs that add a new stress-feature combination."""
    TOKENS = (
        "Symbol.toPrimitive", "valueOf", "toString", "gc(", "ArrayBuffer",
        "SharedArrayBuffer", "TypedArray", "Proxy(", "Object.defineProperty",
        "Reflect.", "Intl.", "WebAssembly.",
    )

    def __init__(self):
        self.seen: set[str] = set()

    def key(self, source: str) -> str:
        features = tuple(sorted(t for t in self.TOKENS if t in source))
        size_bucket = min(len(source) // 1024, 64)
        return hashlib.sha256((repr(features) + ":" + str(size_bucket)).encode()).hexdigest()[:20]

    def interesting(self, source: str, exploration_rate: float = 0.0, rng=None) -> bool:
        key = self.key(source)
        if key not in self.seen:
            self.seen.add(key)
            return True
        return bool(rng and rng.random() < exploration_rate)


class CrashDeduplicator:
    """Atomically claim a crash signature across multiple workers."""
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def claim(self, signature: str) -> bool:
        if not signature:
            return False
        marker = self.directory / ("crash-" + signature + ".seen")
        try:
            fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except OSError:
            return True


class TimeoutStore:
    """Persist a bounded number of timed-out programs for later analysis."""
    def __init__(self, directory: Path, limit: int = 64):
        self.directory = Path(directory)
        self.limit = max(1, limit)
        self.count = 0
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, source: str, worker: int) -> Path | None:
        if self.count >= self.limit:
            return None
        digest = hashlib.sha256(source.encode()).hexdigest()[:20]
        path = self.directory / ("hang-" + str(worker) + "-" + digest + ".js")
        if not path.exists():
            path.write_text(source + "\n/* timeout */\n", encoding="utf-8")
            self.count += 1
        return path
