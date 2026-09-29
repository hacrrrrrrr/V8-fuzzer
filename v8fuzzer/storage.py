"""Content-addressed corpus and crash storage."""

from __future__ import annotations

import hashlib
from pathlib import Path


class Storage:
    def __init__(self, corpus_dir="corpus", crash_dir="crashes"):
        self.corpus_dir = Path(corpus_dir)
        self.crash_dir = Path(crash_dir)
        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        self.crash_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def digest(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def store_program(self, source: str, prefix="input") -> Path:
        digest = self.digest(source)[:24]
        path = self.corpus_dir / f"{prefix}-{digest}.js"
        if not path.exists():
            path.write_text(source, encoding="utf-8")
        return path

    def store_crash(self, source: str, diagnostics: str, prefix="crash") -> Path:
        digest = self.digest(source)[:24]
        path = self.crash_dir / f"{prefix}-{digest}.js"
        payload = source + "\n\n/*\nFUZZ TRIAGE\n" + diagnostics.replace("*/", "* /")
        path.write_text(payload + "\n*/\n", encoding="utf-8")
        return path
