#!/usr/bin/env python3
"""
V8-Fuzzer: lightweight Fuzzilli-style JavaScript fuzzing framework.

The design follows the same broad architecture used by modern JS fuzzers:
program generation -> IR-like snippets -> mutations -> corpus -> execution ->
feedback -> interesting-input retention -> minimization -> crash triage.

It intentionally stays dependency-free and memory bounded for small laptops.
It is not Fuzzilli and does not copy Fuzzilli source code.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import random
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ----------------------------- Configuration -----------------------------

D8_PATH = os.environ.get("D8_PATH", "./d8")
TIMEOUT = float(os.environ.get("V8_FUZZ_TIMEOUT", "5"))
MAX_PROGRAM = int(os.environ.get("V8_FUZZ_MAX_PROGRAM", str(48 * 1024)))
MAX_CORPUS = int(os.environ.get("V8_FUZZ_MAX_CORPUS", "256"))
ITERATIONS = int(os.environ.get("V8_FUZZ_ITERS", "0"))
WARMUP = int(os.environ.get("V8_FUZZ_WARMUP", "500"))
SEED_DIR = Path(os.environ.get("V8_FUZZ_SEEDS", "seeds"))
CORPUS_DIR = Path(os.environ.get("V8_FUZZ_CORPUS", "corpus"))
CRASH_DIR = Path(os.environ.get("V8_FUZZ_CRASHES", "crashes"))
META_DIR = Path(os.environ.get("V8_FUZZ_META", "fuzz-data"))

D8_FLAGS = ("--fuzzing", "--expose-gc", "--allow-natives-syntax")

CRASH_WORDS = (
    "AddressSanitizer", "UndefinedBehaviorSanitizer", "heap-use-after-free",
    "heap-buffer-overflow", "stack-buffer-overflow", "use-after-poison",
    "Segmentation fault", "SIGSEGV", "SIGABRT", "SIGBUS", "Fatal error",
    "Debug check failed", "CHECK failed", "DCHECK", "invalid read",
    "invalid write",
)


# ------------------------------ Memory model ------------------------------

def available_ram_mb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return 2048


def worker_count() -> int:
    forced = os.environ.get("V8_FUZZ_WORKERS")
    if forced:
        return max(1, int(forced))
    ram = available_ram_mb()
    cpu = os.cpu_count() or 1
    if ram <= 3072:
        return 1
    if ram <= 6144:
        return min(2, cpu)
    return min(4, max(1, cpu // 2))


# ------------------------------- Program IR -------------------------------

@dataclass(frozen=True)
class Fragment:
    name: str
    source: str
    weight: int = 1


VALUES = (
    "0", "1", "-1", "2", "0x7fffffff", "0x80000000", "0xffffffff",
    "NaN", "Infinity", "-Infinity", "1.5", "-1.5",
)

TARGETS = (
    "function target(a, x) { return a.fill(1, x, x + 2); }",
    "function target(a, x) { return a.copyWithin(x, 0, 2); }",
    "function target(a, x) { return a.includes(x, x); }",
    "function target(a, x) { return a.indexOf(x, x); }",
    "function target(a, x) { return a.lastIndexOf(x, x); }",
    "function target(s, x) { return s.charAt(x); }",
    "function target(a, x) { return new Int32Array(a).slice(x, x + 2); }",
    "function target(a, x) { const t = new Uint8Array(64); t.set(a, x); return t[0]; }",
)

SETUPS = (
    "const victim = new Array(64).fill(0);",
    "const victim = Array.from({length: 96}, (_, i) => i);",
    "const victim = new Int32Array(96);",
    "const victim = new Uint8Array(128);",
    "const victim = new Float64Array(64);",
)

CALLBACKS = (
    """const trigger = { valueOf() {
  churn(12); shapeChurn(this, 32); gcBurst(); return 1;
}};""",
    """const trigger = { toString() {
  churn(12); shapeChurn(this, 32); gcBurst(); return "1";
}};""",
    """const trigger = { [Symbol.toPrimitive](hint) {
  churn(12); shapeChurn(this, 32); gcBurst();
  return hint === "string" ? "1" : 1;
}};""",
)

PROLOGUE = f'''"use strict";
function gcBurst() {{
  if (typeof gc === "function") {{ gc(); }}
}}
function churn(n) {{
  const a = [];
  for (let i = 0; i < n; i++) {{
    a.push((i & 1) ? new Array(8 + (i & 15)).fill(i)
                   : new ArrayBuffer(128 + ((i * 31) & 1023)));
  }}
  for (let i = 0; i < a.length; i += 2) a[i] = null;
  gcBurst();
  return a;
}}
function shapeChurn(o, n) {{
  for (let i = 0; i < n; i++) {{
    const k = "p" + i;
    o[k] = i;
    if ((i & 3) === 1) delete o[k];
  }}
  return o;
}}
function warm(fn, arg) {{
  let x = 0;
  for (let i = 0; i < {WARMUP}; i++) {{
    try {{ x ^= fn(arg) | 0; }} catch (_) {{}}
  }}
  return x;
}}
'''


# ------------------------------- Mutations --------------------------------

def mutate_literals(source: str, rng: random.Random) -> str:
    replacement = rng.choice(VALUES)
    patterns = ("0xffffffff", "0x80000000", "0x7fffffff", "96", "64", "128")
    pattern = rng.choice(patterns)
    return source.replace(pattern, replacement, 1)


def mutate_loop(source: str, rng: random.Random) -> str:
    return re.sub(
        r"round < \d+",
        f"round < {1 + rng.randrange(7)}",
        source,
        count=1,
    )


def mutate_gc(source: str, rng: random.Random) -> str:
    if "gcBurst();" not in source:
        return source
    parts = source.split("gcBurst();")
    if len(parts) <= 1:
        return source
    index = rng.randrange(1, len(parts))
    return "gcBurst();".join(parts[:index]) + "gcBurst();\ngcBurst();" + "gcBurst();".join(parts[index:])


def splice(a: str, b: str, rng: random.Random) -> str:
    aa = a.splitlines()
    bb = b.splitlines()
    if len(aa) < 8 or len(bb) < 8:
        return a
    left = rng.randrange(2, len(aa) - 2)
    right = rng.randrange(2, len(bb) - 2)
    return "\n".join(aa[:left] + bb[right:])


MUTATORS = (mutate_literals, mutate_loop, mutate_gc)


def mutate(source: str, corpus: list[str], rng: random.Random) -> str:
    result = source
    count = 1 + rng.randrange(3)
    for _ in range(count):
        result = rng.choice(MUTATORS)(result, rng)
    if corpus and rng.random() < 0.25:
        result = splice(result, rng.choice(corpus), rng)
    return result[:MAX_PROGRAM]


# ------------------------------ Generation --------------------------------

def generate(rng: random.Random, number: int) -> str:
    target = rng.choice(TARGETS)
    setup = rng.choice(SETUPS)
    callback = rng.choice(CALLBACKS)
    value = rng.choice(VALUES)
    rounds = 1 + rng.randrange(6)

    return f'''// V8-Fuzzer program {number} seed={rng.getrandbits(64):016x}
{PROLOGUE}
{target}
{setup}
const receiver = victim;
const marker = {value};
{callback}

warm(target, marker);

try {{
  for (let round = 0; round < {rounds}; round++) {{
    churn(8 + (round & 7));
    shapeChurn({{}}, 16 + round);
    target(receiver, trigger);
    target(receiver, marker);
    gcBurst();
  }}
}} catch (_) {{}}

let s = "0123456789".repeat(16 + ({number} & 15));
try {{ target(s, trigger); }} catch (_) {{}}
s = null;
gcBurst();
'''[:MAX_PROGRAM]


# ------------------------------ Execution ---------------------------------

@dataclass
class Result:
    crashed: bool
    timeout: bool
    returncode: int
    output: str
    signature: str


def crash_signature(output: str, returncode: int) -> str:
    for word in CRASH_WORDS:
        if word.lower() in output.lower():
            lines = [x.strip() for x in output.splitlines()
                     if word.lower() in x.lower()]
            return hashlib.sha256("\n".join(lines[:4]).encode()).hexdigest()[:20]
    if returncode in (134, 139, -signal.SIGSEGV, -signal.SIGABRT, -signal.SIGBUS):
        return f"signal-{returncode}"
    return ""


def execute(source: str) -> Result:
    try:
        p = subprocess.Popen(
            (D8_PATH, *D8_FLAGS, "-"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        try:
            out, err = p.communicate(source, timeout=TIMEOUT)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = p.communicate()

        output = "=== STDOUT ===\n" + out + "\n=== STDERR ===\n" + err
        crashed = False if timed_out else bool(crash_signature(output, p.returncode))
        return Result(crashed, timed_out, p.returncode, output,
                      crash_signature(output, p.returncode))
    except OSError as exc:
        return Result(False, False, 127, str(exc), "")


# ------------------------------- Corpus -----------------------------------

@dataclass
class CorpusEntry:
    source: str
    digest: str
    size: int
    executions: int = 0
    crashes: int = 0


class Corpus:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.entries: list[CorpusEntry] = []
        self.seen: set[str] = set()
        self.load()

    def load(self) -> None:
        for directory in (SEED_DIR, CORPUS_DIR):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.js"))[:MAX_CORPUS]:
                try:
                    source = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.add(source, persist=False)

    def add(self, source: str, persist: bool = True) -> bool:
        if not source or len(source.encode()) > MAX_PROGRAM:
            return False
        digest = hashlib.sha256(source.encode()).hexdigest()
        if digest in self.seen:
            return False
        self.seen.add(digest)
        self.entries.append(CorpusEntry(source, digest[:20], len(source)))
        if len(self.entries) > MAX_CORPUS:
            victim = self.rng.randrange(len(self.entries))
            self.entries.pop(victim)
        if persist:
            CORPUS_DIR.mkdir(parents=True, exist_ok=True)
            path = CORPUS_DIR / f"input-{digest[:20]}.js"
            if not path.exists():
                path.write_text(source, encoding="utf-8")
        return True

    def choose(self) -> str:
        if not self.entries:
            return ""
        # Small-program bias keeps the 2 GB mode cheap while still exploring
        # older inputs.
        weights = [max(1, 8192 - min(e.size, 8192)) for e in self.entries]
        return self.rng.choices(self.entries, weights=weights, k=1)[0].source

    def __len__(self) -> int:
        return len(self.entries)


# ----------------------------- Minimization --------------------------------

def minimize(source: str, predicate, budget: int = 80) -> str:
    """Simple line-chunk reducer for reproducible native crashes."""
    lines = source.splitlines()
    if len(lines) < 4:
        return source
    changed = True
    attempts = 0
    chunk = max(1, len(lines) // 2)
    while changed and attempts < budget and chunk >= 1:
        changed = False
        i = 0
        while i < len(lines) and attempts < budget:
            candidate = lines[:i] + lines[i + chunk:]
            attempts += 1
            if len("\n".join(candidate).encode()) <= MAX_PROGRAM and predicate("\n".join(candidate)):
                lines = candidate
                changed = True
            else:
                i += chunk
        if not changed:
            chunk //= 2
    return "\n".join(lines) + "\n"


# ------------------------------- Triage ------------------------------------

def save_crash(source: str, result: Result, worker: int, minimized: bool = False) -> Path:
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.encode()).hexdigest()[:20]
    suffix = "-min" if minimized else ""
    path = CRASH_DIR / f"crash-{worker}-{int(time.time())}-{digest}{suffix}.js"
    text = source + "\n/*\nFUZZ TRIAGE\n" + result.output.replace("*/", "* /") + "\n*/\n"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------- Worker -----------------------------------

def worker(worker_id: int, stop: mp.Event) -> None:
    seed = (time.time_ns() ^ (os.getpid() << 16) ^ worker_id) & ((1 << 64) - 1)
    rng = random.Random(seed)
    corpus = Corpus(rng)
    crashes = 0
    timeouts = 0
    executions = 0

    while not stop.is_set():
        if ITERATIONS and executions >= ITERATIONS:
            break

        if len(corpus) and rng.random() < 0.82:
            source = mutate(corpus.choose(), corpus=[e.source for e in corpus.entries], rng=rng)
        else:
            source = generate(rng, executions)

        result = execute(source)
        executions += 1

        if result.timeout:
            timeouts += 1
            continue

        if result.crashed:
            crashes += 1

            def same_crash(candidate: str) -> bool:
                r = execute(candidate)
                return r.crashed and r.signature == result.signature

            minimized = minimize(source, same_crash)
            save_crash(source, result, worker_id)
            if minimized != source:
                min_result = execute(minimized)
                save_crash(minimized, min_result, worker_id, minimized=True)
            print(
                f"[worker {worker_id}] CRASH #{crashes} "
                f"signature={result.signature} corpus={len(corpus)}",
                flush=True,
            )
            continue

        # Keep generated programs and mutated programs. This is the corpus
        # feedback layer; a future native coverage provider can replace this
        # heuristic with edge/new-feature feedback without changing the loop.
        if rng.random() < 0.18:
            corpus.add(source)

        if executions % 100 == 0:
            print(
                f"[worker {worker_id}] exec={executions} corpus={len(corpus)} "
                f"crashes={crashes} timeouts={timeouts}",
                flush=True,
            )


# -------------------------------- Main -------------------------------------

def main() -> int:
    if not Path(D8_PATH).is_file():
        print(f"error: d8 not found: {D8_PATH}", file=sys.stderr)
        return 2

    for directory in (CORPUS_DIR, CRASH_DIR, META_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    workers = worker_count()
    stop = mp.Event()
    processes = []

    def shutdown(*_):
        stop.set()
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join(timeout=1)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(
        f"[+] V8-Fuzzer workers={workers} RAM~{available_ram_mb()}MB "
        f"timeout={TIMEOUT}s corpus_limit={MAX_CORPUS}",
        flush=True,
    )
    print("[+] architecture: generate -> mutate -> execute -> triage -> corpus", flush=True)
    print("[+] d8 flags: " + " ".join(D8_FLAGS), flush=True)

    for worker_id in range(workers):
        p = mp.Process(target=worker, args=(worker_id, stop))
        p.start()
        processes.append(p)

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        shutdown()

    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
