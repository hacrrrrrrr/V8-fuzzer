"""Interestingness evaluation for generated JavaScript programs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Evaluation:
    interesting: bool
    score: int
    reason: str
    fingerprint: str


class Evaluator:
    """Score samples using portable execution feedback.

    Native edge coverage is optional and intentionally not required. The
    evaluator can consume a coverage text/file supplied by an external V8
    build, while still providing useful heuristics on ordinary d8 builds.
    """

    _TOKENS = (
        "AddressSanitizer", "UndefinedBehaviorSanitizer", "Fatal error",
        "DCHECK", "CHECK failed", "Segmentation fault", "SIGSEGV",
        "heap-use-after-free", "heap-buffer-overflow", "invalid read",
        "invalid write",
    )

    def evaluate(self, source: str, output: str, returncode: int,
                 timeout: bool = False, coverage: str = "") -> Evaluation:
        if timeout:
            return Evaluation(False, 0, "timeout", self._hash("timeout", source))

        lower = output.lower()
        hits = [t for t in self._TOKENS if t.lower() in lower]
        nonzero = returncode not in (0, None)

        # Feature fingerprint is deliberately stable across runs.
        features = self._source_features(source)
        coverage_hash = self._hash(coverage) if coverage else ""
        fingerprint = self._hash("|".join(sorted(hits)), str(returncode),
                                  ",".join(features), coverage_hash)

        score = len(features) + len(hits) * 100
        if nonzero:
            score += 10
        if coverage:
            score += 25

        reason = "native-diagnostic" if hits else (
            "nonzero-exit" if nonzero else
            "new-program-features" if features else "ordinary"
        )
        return Evaluation(bool(hits or nonzero or features), score, reason,
                          fingerprint)

    @staticmethod
    def _source_features(source: str) -> list[str]:
        patterns = (
            r"Symbol\.toPrimitive", r"\.valueOf\s*\(", r"\.toString\s*\(",
            r"\bgc\s*\(", r"ArrayBuffer", r"SharedArrayBuffer",
            r"TypedArray|Uint8Array|Int32Array|Float64Array",
            r"Proxy\s*\(", r"Object\.defineProperty",
            r"\bReflect\.", r"\bIntl\.", r"\bWebAssembly\.",
        )
        return [p for p in patterns if re.search(p, source)]

    @staticmethod
    def _hash(*parts: str) -> str:
        h = hashlib.sha256()
        for part in parts:
            h.update(part.encode("utf-8", "replace"))
            h.update(b"\0")
        return h.hexdigest()[:24]
