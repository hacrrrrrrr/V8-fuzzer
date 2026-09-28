#!/usr/bin/env python3
"""
Dependency-free V8 d8 structural mutation fuzzer.
"""

from __future__ import annotations
import hashlib
import multiprocessing as mp
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

D8_PATH = "./d8"
WORKERS = max(1, os.cpu_count() or 1)
TIMEOUT_SECONDS = 5.0
ITERATIONS_PER_WORKER = 0
CRASH_DIR = Path("crashes")
WARMUP_ITERS = 2200
MAX_CASE_BYTES = 64 * 1024

D8_FLAGS = (
    "--fuzzing",
    "--expose-gc",
    "--allow-natives-syntax",
)

CRASH_MARKERS = (
    "AddressSanitizer", "LeakSanitizer", "UndefinedBehaviorSanitizer",
    "heap-use-after-free", "stack-use-after-return", "stack-buffer-overflow",
    "heap-buffer-overflow", "use-after-poison", "Segmentation fault", "SIGSEGV",
    "SIGABRT", "Fatal error", "Debug check failed", "DCHECK", "ASSERT",
    "CHECK failed", "Check failed", "invalid read", "invalid write",
)

HEADER = r'''
"use strict";

function gcBurst() {
  if (typeof gc === "function") { gc(); gc(); }
}

function churn(count) {
  const keep = [];
  for (let i = 0; i < count; i++) {
    if ((i & 1) === 0) keep.push(new ArrayBuffer(0x100 + ((i * 37) & 0x7ff)));
    else keep.push(new Array(8 + (i & 31)).fill(i));
  }
  for (let i = 0; i < keep.length; i += 2) keep[i] = null;
  gcBurst();
  return keep;
}

function shapeChurn(o, rounds) {
  for (let i = 0; i < rounds; i++) {
    const k = "p" + i;
    o[k] = i;
    if ((i & 3) === 1) delete o[k];
  }
  o.stable = 0x41414141;
  return o;
}

function warm(fn, arg) {
  let x = 0;
  for (let i = 0; i < __WARMUP__; i++) {
    try { x ^= fn(arg) | 0; } catch (_) {}
  }
  return x;
}

function conversionBomb(tag) {
  const pool = churn(24);
  const o = {};
  shapeChurn(o, 96);
  gcBurst();
  return tag.length + pool.length + (o.stable | 0);
}
'''.replace("__WARMUP__", str(WARMUP_ITERS))

TARGETS = (
    r'''function target(a, x) { return a.fill(1, x, x + 2); }''',
    r'''function target(a, x) { return a.lastIndexOf(x, x); }''',
    r'''function target(s, x) { return s.charAt(x); }''',
    r'''function target(a, x) { return new Int32Array(a).slice(x, x + 2); }''',
    r'''function target(a, x) { const t = new Uint8Array(64); t.set(a, x); return t[0]; }''',
    r'''function target(a, x) { return a.copyWithin(x, 0, 2); }''',
    r'''function target(a, x) { return a.includes(x, x); }''',
    r'''function target(a, x) { return a.indexOf(x, x); }''',
)

PRIMITIVES = (
    "0", "1", "-1", "NaN", "Infinity", "-Infinity",
    "0x7fffffff", "0x80000000", "0xffffffff", "1.5", "-1.5",
    "2**31", "-2**31",
)

def conversion_object(style: int, seed: int) -> str:
    if style == 0:
        return r'''
const trigger = {
  valueOf() {
    conversionBomb("valueOf");
    return 1;
  }
};
'''
    if style == 1:
        return r'''
const trigger = {
  toString() {
    conversionBomb("toString");
    return "1";
  }
};
'''
    if style == 2:
        return r'''
const trigger = {
  [Symbol.toPrimitive](hint) {
    conversionBomb("toPrimitive:" + hint);
    return hint === "string" ? "1" : 1;
  }
};
'''
    return f'''
const trigger = {{
  valueOf() {{
    const q = churn({8 + (seed & 15)});
    q.length = {1 + (seed & 31)};
    shapeChurn(this, {32 + (seed & 63)});
    gcBurst();
    return {seed & 3};
  }},
  toString() {{
    gcBurst();
    return "1";
  }}
}};
'''

def make_case(rng: random.Random, case_id: int) -> str:
    seed = rng.getrandbits(32)
    target = rng.choice(TARGETS)
    primitive = rng.choice(PRIMITIVES)
    trigger = conversion_object(rng.randrange(4), seed)

    array_setup = rng.choice((
        "const victim = new Array(64).fill(0);",
        "const victim = Array.from({length: 96}, (_, i) => i);",
        "const victim = new Int32Array(96);",
        "const victim = new Uint8Array(128);",
        "const victim = new Float64Array(64);",
        "const victim = new ArrayBuffer(512);",
    ))
    receiver = "new Int32Array(victim)" if "ArrayBuffer" in array_setup else "victim"

    tail = rng.choice((
        r'''
const tail = [];
for (let i = 0; i < 48; i++) {
  const o = {a: i, b: i + 1};
  if (i & 1) delete o.a;
  o["x" + i] = i;
  tail.push(o);
}
gcBurst();
''',
        r'''
const ta = new Uint16Array(96);
for (let i = 0; i < ta.length; i++) ta[i] = i;
try { target(ta, trigger); } catch (_) {}
gcBurst();
''',
        r'''
let s = "0123456789".repeat(32);
try { target(s, trigger); } catch (_) {}
s = null;
gcBurst();
''',
    ))

    source = f'''// V8 structural fuzz case: seed=0x{seed:08x}, id={case_id}
{HEADER}
{target}
{array_setup}
const receiver = {receiver};
const marker = {primitive};
{trigger}

warm(target, marker);

try {{
  for (let round = 0; round < 4; round++) {{
    churn(12 + (round & 3));
    shapeChurn({{}}, 24 + round);
    target(receiver, trigger);
    target(receiver, marker);
    gcBurst();
  }}
}} catch (e) {{
  // Conversion exceptions are expected; native diagnostics are collected outside d8.
}}

{tail}
'''
    return source[:MAX_CASE_BYTES]

def looks_like_crash(returncode: int, output: str) -> bool:
    # SIGKILL (-9) is deliberately generated by this fuzzer when a testcase
    # exceeds TIMEOUT_SECONDS, so it must never be classified as a crash.
    if returncode == -signal.SIGKILL:
        return False
    if returncode in (-signal.SIGSEGV, -signal.SIGABRT, -signal.SIGBUS):
        return True
    if returncode in (134, 139, 3221225477, 3221225781):
        return True
    lowered = output.lower()
    return any(marker.lower() in lowered for marker in CRASH_MARKERS)

def run_case(source: str) -> Tuple[bool, str, int, bool]:
    try:
        proc = subprocess.Popen(
            (D8_PATH, *D8_FLAGS, "-"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        try:
            stdout, stderr = proc.communicate(source, timeout=TIMEOUT_SECONDS)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()

        output = "=== STDOUT ===\n" + stdout + "\n=== STDERR ===\n" + stderr
        # A timeout owns the SIGKILL we just issued; do not pass it to crash
        # triage even if the resulting return code is -9.
        crashed = False if timed_out else looks_like_crash(proc.returncode, output)
        return crashed, output, proc.returncode, timed_out
    except OSError as exc:
        return False, f"fuzzer execution error: {exc}", 127, False

def save_crash(source: str, diagnostics: str, worker_id: int) -> Path:
    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    path = CRASH_DIR / f"crash-{time.time_ns()}-{worker_id}-{digest}.js"
    comment = "\n\n/*\nV8 FUZZER TRIAGE LOG\n=====================\n"
    comment += diagnostics.replace("*/", "* /") + "\n*/\n"
    path.write_text(source + comment, encoding="utf-8")
    return path

def worker(worker_id: int, stop: mp.Event) -> int:
    seed = (time.time_ns() ^ (os.getpid() << 17) ^
            (worker_id * 0x9E3779B97F4A7C15)) & ((1 << 64) - 1)
    rng = random.Random(seed)
    count = crashes = timeouts = 0

    while not stop.is_set():
        if ITERATIONS_PER_WORKER and count >= ITERATIONS_PER_WORKER:
            break

        case = make_case(rng, count)
        crashed, diagnostics, returncode, timed_out = run_case(case)
        count += 1

        if timed_out:
            timeouts += 1
            print(f"[worker {worker_id}] TIMEOUT #{timeouts} cases={count}",
                  flush=True)

        if crashed:
            crashes += 1
            path = save_crash(case, diagnostics, worker_id)
            print(f"[worker {worker_id}] CRASH #{crashes}: {path} "
                  f"(returncode={returncode})", flush=True)
        elif count % 100 == 0:
            print(f"[worker {worker_id}] cases={count} crashes={crashes} "
                  f"timeouts={timeouts}", flush=True)

    return count

def main() -> int:
    if not Path(D8_PATH).is_file():
        print(f"error: d8 not found at {D8_PATH}", file=sys.stderr)
        return 2

    CRASH_DIR.mkdir(exist_ok=True)
    stop = mp.Event()
    processes = []

    def shutdown(*_args):
        stop.set()
        for p in processes:
            if p.is_alive():
                p.terminate()
        for p in processes:
            p.join(timeout=1.0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"[+] V8 d8 fuzzer: workers={WORKERS}, timeout={TIMEOUT_SECONDS}s", flush=True)
    print(f"[+] target: {D8_PATH}", flush=True)
    print("[+] progress: each worker reports every completed testcase/timeout", flush=True)

    for worker_id in range(WORKERS):
        p = mp.Process(target=worker, args=(worker_id, stop), daemon=False)
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
