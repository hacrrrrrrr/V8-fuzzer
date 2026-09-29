"""Corpus-aware structural mutation engine."""

from __future__ import annotations

import random
import re


class MutationEngine:
    def __init__(self, max_program: int = 48 * 1024):
        self.max_program = max_program

    def mutate(self, source: str, corpus: list[str], rng: random.Random) -> str:
        result = source
        for _ in range(1 + rng.randrange(4)):
            choice = rng.randrange(4)
            if choice == 0:
                result = self._replace_boundary(result, rng)
            elif choice == 1:
                result = self._change_loop(result, rng)
            elif choice == 2:
                result = self._duplicate_statement(result, rng)
            elif corpus:
                result = self._splice(result, rng.choice(corpus), rng)
        return result[:self.max_program]

    def _replace_boundary(self, source, rng):
        values = ("-1", "0", "1", "1.5", "NaN", "Infinity",
                  "0x7fffffff", "0x80000000", "0xffffffff")
        return re.sub(r"0xffffffff|0x80000000|0x7fffffff|-1|1", 
                      lambda _: rng.choice(values), source, count=1)

    def _change_loop(self, source, rng):
        return re.sub(r"round < \d+", f"round < {1 + rng.randrange(8)}",
                      source, count=1)

    def _duplicate_statement(self, source, rng):
        lines = source.splitlines()
        candidates = [i for i, line in enumerate(lines)
                      if line.strip() and not line.lstrip().startswith("//")]
        if not candidates:
            return source
        i = rng.choice(candidates)
        lines.insert(i, lines[i])
        return "\n".join(lines)

    def _splice(self, left, right, rng):
        a, b = left.splitlines(), right.splitlines()
        if len(a) < 6 or len(b) < 6:
            return left
        cut_a = rng.randrange(2, len(a) - 2)
        cut_b = rng.randrange(2, len(b) - 2)
        return "\n".join(a[:cut_a] + b[cut_b:])
