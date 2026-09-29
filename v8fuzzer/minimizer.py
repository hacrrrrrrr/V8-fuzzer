"""Generic delta-debugging minimizer."""

from __future__ import annotations


class Minimizer:
    def __init__(self, budget: int = 80, max_bytes: int = 48 * 1024):
        self.budget = max(1, budget)
        self.max_bytes = max_bytes

    def minimize(self, source: str, predicate) -> str:
        lines = source.splitlines()
        if len(lines) < 4:
            return source

        attempts = 0
        chunk = max(1, len(lines) // 2)
        while chunk >= 1 and attempts < self.budget:
            changed = False
            i = 0
            while i < len(lines) and attempts < self.budget:
                candidate_lines = lines[:i] + lines[i + chunk:]
                candidate = "\n".join(candidate_lines) + "\n"
                attempts += 1
                if len(candidate.encode()) <= self.max_bytes and predicate(candidate):
                    lines = candidate_lines
                    changed = True
                else:
                    i += chunk
            if not changed:
                chunk //= 2
        return "\n".join(lines) + "\n"
