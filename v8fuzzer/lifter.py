"""Small source lifter for the fuzzer's program fragments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Program:
    fragments: tuple[str, ...]
    trailer: str = ""


class Lifter:
    """Translate the fuzzer's fragment representation into JavaScript."""

    def lift(self, program: Program) -> str:
        parts = ['"use strict";']
        parts.extend(x.rstrip() for x in program.fragments if x.strip())
        if program.trailer.strip():
            parts.append(program.trailer.rstrip())
        return "\n\n".join(parts) + "\n"

    def from_source(self, source: str) -> Program:
        return Program((source,))
