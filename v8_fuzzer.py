# V8-Fuzzer v2.2.0\n# Improvement tracking: https://github.com/hacrrrrrrr/V8-fuzzer/issues/1\n# This release is maintained as the implementation work for Issue #1.\n#!/usr/bin/env python3
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
import platform
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

VERSION = "2.2.0"
ISSUE_URL = "https://github.com/hacrrrrrrr/V8-fuzzer/issues/1"
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
MINIMIZE = os.environ.get("V8_FUZZ_MINIMIZE", "1").lower() not in {"0", "false", "no"}
MINIMIZE_BUDGET = max(1, int(os.environ.get("V8_FUZZ_MINIMIZE_BUDGET", "40")))

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
    """Best-effort physical/available RAM detection without third-party modules."""
    system = platform.system()

    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        except (OSError, ValueError):
            pass

    if system == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return max(512, status.ullAvailPhys // (1024 * 1024))
        except (AttributeError, OSError, TypeError):
            pass

    if system == "Darwin":
        try:
            total = int(subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], text=True
            ).strip())
            # macOS does not expose a simple portable MemAvailable equivalent;
            # use a conservative fraction of physical memory.
            return max(512, (total // (1024 * 1024)) // 2)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    # Safe fallback for other Unix-like systems and unusual environments.
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


def resolve_d8_path() -> str:
    """Resolve the configured d8 path, including Windows d8.exe."""
    configured = Path(D8_PATH)
    if configured.is_file():
        return str(configured)
    if os.name == "nt" and D8_PATH == "./d8":
        windows_d8 = Path("./d8.exe")
        if windows_d8.is_file():
            return str(windows_d8)
    return D8_PATH


def terminate_process_tree(process: subprocess.Popen) -> None:
    """Kill a d8 process and any descendants on POSIX and Windows."""
    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def popen_kwargs() -> dict:
    """Return platform-specific process-isolation settings."""
    if os.name == "nt":
        return {
            "creationflags": getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        }
    return {"start_new_session": True}


# ------------------------------- Program IR -------------------------------

@dataclass(frozen=True)
class Fragment:
    name: str
    source: str
    weight: int = 1


BUG_CLASS_SEEDS = (
    """function boundsPressure() {
  const a = new Array(8);
  for (const i of [-1, 0, 1, 7, 8, 0x7fffffff]) {
    try { a[i] = i; void a[i]; } catch (_) {}
  }
} boundsPressure();""",
    """function typedBounds() {
  const u = new Uint32Array(new ArrayBuffer(64));
  for (const i of [-1, 0, 1, 15, 16, 0x7fffffff]) {
    try { u[i] = 0x41414141; void u[i]; } catch (_) {}
  }
} typedBounds();""",
    """function representationFlip(x) {
  const a = [1,2,3,4];
  for (let i=0;i<200;i++) {
    a[0] = (i & 1) ? x : i;
    a[1] = i + 0.5;
  }
  return a;
}
for (const x of [1, 1.5, "x", {}, null]) {
  try { representationFlip(x); } catch (_) {}
}""",
    """function shapeFlip() {
  function C() { this.x = 1; }
  const a = new C(), b = new C();
  for (let i=0;i<300;i++) {
    if (i & 1) { a.y = i; delete a.y; }
    else { b.z = i; delete b.z; }
    a.x = i; b.x = i;
  }
  return a.x + b.x;
}
shapeFlip();""",
    """function lifetimePressure() {
  let refs = [];
  for (let i=0;i<128;i++) {
    let o = {x:i, buf:new ArrayBuffer(256)};
    refs.push(new WeakRef(o));
    if ((i & 7) === 0) {
      o = null;
      if (typeof gc === "function") gc();
    }
  }
  if (typeof gc === "function") for (let i=0;i<4;i++) gc();
  return refs.length;
}
try { lifetimePressure(); } catch (_) {}""",
    """function callbackLifetime() {
  const a = new Array(64).fill(1);
  const x = { valueOf() {
    const garbage = [];
    for (let i=0;i<64;i++) garbage.push({i, b:new ArrayBuffer(128)});
    if (typeof gc === "function") gc();
    a.length = (a.length ^ 1) & 63;
    return 1;
  }};
  try { a.fill(7, x, x); } catch (_) {}
}
callbackLifetime();""",
    """function builtinReentry() {
  const a = [1,2,3,4,5,6];
  const receiver = {
    length: 6, 0:1, 1:2, 2:3,
    get 3() { a.pop(); delete this[2]; return 4; }
  };
  try { Array.prototype.join.call(receiver, ","); } catch (_) {}
}
builtinReentry();""",
    """function invariantPressure() {
  const a = [];
  for (let i=0;i<256;i++) {
    a.length = i;
    if ((i & 3) === 0) a.push(i);
    if ((i & 7) === 0) a.length = Math.max(0, i >>> 1);
    Object.defineProperty(a, "x", {value:i, configurable:true, writable:true});
    delete a.x;
  }
}
try { invariantPressure(); } catch (_) {}""",
    """const locales = [
  "fa-IR-u-ca-persian-nu-arabext",
  "en-US-u-ca-gregory",
  "ar-EG-u-nu-arab",
  "th-TH-u-ca-buddhist"
];
for (const locale of locales) {
  try {
    const f = new Intl.DateTimeFormat(locale, {
      dateStyle:"full", timeStyle:"long", calendar:"persian"
    });
    const d = new Date((Math.random()*2-1)*8.64e15);
    f.format(d);
    f.resolvedOptions();
    f.formatRange(d, new Date(d.getTime()+86400000));
  } catch (_) {}
}""",
)

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
    special = rng.choice(BUG_CLASS_SEEDS) if rng.random() < 0.30 else ""
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
    if (special) { try { eval(special); } catch (_) {} }
    target(receiver, marker);
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
            (resolve_d8_path(), *D8_FLAGS, "-"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            **popen_kwargs(),
        )
        try:
            out, err = p.communicate(source, timeout=TIMEOUT)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            terminate_process_tree(p)
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
    base_seed = os.environ.get("V8_FUZZ_SEED")
    if base_seed is not None:
        try:
            seed = int(base_seed, 0) ^ (worker_id * 0x9E3779B97F4A7C15)
        except ValueError:
            seed = hash(base_seed) ^ worker_id
    else:
        seed = time.time_ns() ^ (os.getpid() << 16) ^ worker_id
    seed &= (1 << 64) - 1
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

            save_crash(source, result, worker_id)
            if MINIMIZE:
                minimized = minimize(source, same_crash, budget=MINIMIZE_BUDGET)
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
    resolved_d8 = resolve_d8_path()
    if not Path(resolved_d8).is_file():
        print(f"error: d8 not found: {D8_PATH}", file=sys.stderr)
        print("hint: on Windows, place d8.exe in the working directory or set D8_PATH.",
              file=sys.stderr)
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
        f"[+] V8-Fuzzer v{VERSION} platform={platform.system()} "
        f"arch={platform.machine()} workers={workers} "
        f"RAM~{available_ram_mb()}MB timeout={TIMEOUT}s "
        f"corpus_limit={MAX_CORPUS}",
        flush=True,
    )
    print("[+] architecture: generate -> mutate -> execute -> evaluate -> corpus -> minimize", flush=True)
    print("[+] modules: MutationEngine, Evaluator, Minimizer, Lifter, Storage, Statistics, ThreadSync, NetworkSync", flush=True)
    print("[+] tracking issue: " + ISSUE_URL, flush=True)
    print(f"[+] minimize_crashes={MINIMIZE} budget={MINIMIZE_BUDGET}", flush=True)
    if os.environ.get("V8_FUZZ_SEED") is not None:
        print("[+] deterministic seed mode enabled", flush=True)
    print("[+] d8: " + resolved_d8, flush=True)
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
