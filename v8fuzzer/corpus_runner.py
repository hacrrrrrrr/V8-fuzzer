"""Corpus/script runner with evaluator feedback."""
from __future__ import annotations
from pathlib import Path
from .evaluator import Evaluator
from .runner import D8Runner
from .storage import Storage

class CorpusRunner:
    def __init__(self, runner=None, evaluator=None, storage=None):
        self.runner = runner or D8Runner()
        self.evaluator = evaluator or Evaluator()
        self.storage = storage or Storage()

    def run_file(self, path: Path):
        source = path.read_text(encoding="utf-8", errors="replace")
        result = self.runner.run(source)
        evaluation = self.evaluator.evaluate(
            source, result["stdout"] + result["stderr"],
            result["returncode"], result["timeout"])
        if evaluation.interesting:
            self.storage.store_program(source, prefix="interesting")
        return evaluation

    def run_directory(self, directory: Path):
        for path in sorted(directory.glob("*.js")):
            yield path, self.run_file(path)
