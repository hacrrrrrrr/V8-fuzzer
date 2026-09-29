"""Optional synchronization primitives.

ThreadSync is process-local and dependency-free. NetworkSync is intentionally
opt-in and only exchanges content-addressed corpus programs over an explicitly
configured TCP peer; it is not enabled by default.
"""

from __future__ import annotations

import hashlib
import socket
import threading


class ThreadSync:
    def __init__(self):
        self._lock = threading.Lock()
        self._seen = set()

    def claim(self, source: str) -> bool:
        digest = hashlib.sha256(source.encode()).hexdigest()
        with self._lock:
            if digest in self._seen:
                return False
            self._seen.add(digest)
            return True


class NetworkSync:
    """Minimal opt-in corpus exchange.

    The caller supplies the peer and framing. No network listener is created
    automatically, and no external service is contacted.
    """

    def __init__(self, host: str, port: int, timeout: float = 1.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, source: str) -> None:
        payload = source.encode("utf-8")
        with socket.create_connection((self.host, self.port), self.timeout) as sock:
            sock.sendall(len(payload).to_bytes(4, "big") + payload)
