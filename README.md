> **Sponsorship / Research Support:** **hunterkritik@gmail.com**  
> Hardware, fuzzing infrastructure, research collaboration, and project sponsorship inquiries are welcome.

# V8 Fuzzer v2.2.0 — Lightweight, Fuzzilli-Inspired d8 Fuzzing

**A small-footprint V8 JavaScript engine fuzzer for authorized local security research.**

> Built for practical fuzzing on ordinary hardware, including laptops with around **2 GB RAM**.

This project uses ideas common to modern JavaScript fuzzers: corpus-based generation, mutation, program diversity, crash isolation, and continuous testcase execution. It is **not a reimplementation of Fuzzilli** and currently does not provide engine coverage feedback.

## v2.0.0 — Cross-platform release — September 2026

- Added a professional seed/corpus taxonomy for boundaries, memory, JIT, runtime, and Intl paths.
- Added dedicated bug-pattern seeds for bounds, representation transitions, shape/prototype changes, GC/lifetime pressure, callback re-entry, and ECMA-402.
- Added Persian-calendar and other Intl date-formatting seeds.
- Fixed the generator integration so specialized seeds are actually executed instead of merely being stored.
- Added cross-platform process and memory handling for Linux, macOS, and Windows.
- Added Windows `d8.exe` discovery and process-tree timeout cleanup.
- Added platform/architecture diagnostics at startup.
- Preserved the 2-GB profile: one worker by default on low-memory systems, bounded corpus, isolated d8 process, and per-testcase timeout.
- Expanded crash triage documentation for sanitizer failures, CHECK/DCHECK/FATAL, SIGSEGV, SIGABRT, and related native failures.

See [`CHANGELOG.md`](CHANGELOG.md) for the complete release history.

## What changed

- RAM-aware worker count; **one worker by default on ~2 GB machines**
- Small rolling corpus plus mutation of previously generated programs
- One isolated d8 process per testcase
- **5-second timeout** by default
- Requested d8 flags only: `--fuzzing --expose-gc --allow-natives-syntax`
- Bounded testcase size and bounded corpus
- Native crash diagnostics saved with reproducing JavaScript
- No third-party Python dependencies

## Architecture

```text
                    ┌──────────────────────┐
                    │ Seeds + small corpus │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Generator + mutator  │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        JS API targets    coercion hooks     edge values
        Array/String      valueOf/toString    int/float
        TypedArrays       Symbol.toPrimitive  boundaries
              └────────────────┼────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │ JIT + GC + shape     │
                    │ and allocation churn │
                    └──────────┬───────────┘
                               │
                               ▼
                 ┌──────────────────────────┐
                 │ Isolated d8 testcase     │
                 │ 5 s timeout / process    │
                 └────────────┬─────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
                 timeout              exit
                    │                   │
                    ▼                   ▼
                 discard         crash/diagnostic?
                                        │
                                        ▼
                                crashes/*.js
                                        │
                                        ▼
                              reproduce / reduce
```

### Memory-aware worker model

```text
              available RAM
                   │
       ┌───────────┼────────────┐
       ▼           ▼            ▼
    <= 3 GB     3–6 GB       > 6 GB
       │           │            │
       ▼           ▼            ▼
    1 worker    max 2       bounded CPU
                              workers
```

Override it explicitly:

```bash
V8_FUZZ_WORKERS=1 python3 v8_fuzzer.py
```

## Fuzzing loop

The lightweight evolutionary loop is:

```text
seed
  ↓
execute
  ↓
generate / mutate
  ↓
execute
  ↓
retain useful program structure
  ↓
mutate again
```

The corpus is intentionally bounded. Without engine coverage instrumentation, retention is heuristic rather than true coverage guidance.

### Conversion and re-entry pressure

Generated objects can implement:

- `valueOf()`
- `toString()`
- `Symbol.toPrimitive`

These callbacks can allocate objects, change shapes, and invoke GC before returning to the builtin path.

```text
JavaScript builtin
      │
      ▼
  conversion
      │
      ▼
 user callback
      │
 ┌────┴───────────────┐
 │ allocation         │
 │ shape mutation     │
 │ garbage collection │
 └────┬───────────────┘
      │
      ▼
 return to builtin
      │
      ▼
 optimized/native path
```

### JIT pressure

The default warm-up is **600 iterations**, reduced from the previous 2,200 to make individual testcases cheaper on small-memory systems.

```bash
V8_FUZZ_WARMUP=300 python3 v8_fuzzer.py
```

## Current target families

- `Array.prototype.fill`
- `Array.prototype.lastIndexOf`
- `String.prototype.charAt`
- TypedArray construction and slicing
- `TypedArray.prototype.set`
- `Array.prototype.copyWithin`
- `Array.prototype.includes`
- `Array.prototype.indexOf`

## Running

Place the V8 shell at `./d8`, then:

```bash
python3 v8_fuzzer.py
```

Typical 2 GB startup:

```text
[+] V8 d8 fuzzer: workers=1, timeout=5.0s, RAM~...
[+] corpus=... target=./d8
```

Bounded campaign:

```bash
V8_FUZZ_WORKERS=1 V8_FUZZ_ITERS=1000 python3 v8_fuzzer.py
```

Replay a saved crash:

```bash
./d8 --fuzzing --expose-gc --allow-natives-syntax crashes/<file>.js
```

## Configuration

| Setting | Default | Purpose |
|---|---:|---|
| `D8_PATH` | `./d8` | V8 shell path |
| `V8_FUZZ_WORKERS` | RAM-aware | Worker count |
| `V8_FUZZ_TIMEOUT` | `5` | Seconds per testcase |
| `V8_FUZZ_ITERS` | `0` | Cases per worker; 0 = unlimited |
| `V8_FUZZ_WARMUP` | `600` | JIT warm-up calls |
| `V8_FUZZ_SEED_DIR` | `seeds` | Initial seeds |
| `V8_FUZZ_CORPUS_DIR` | `corpus` | Persistent corpus |
| `V8_FUZZ_CRASH_DIR` | `crashes` | Crash output |

## Why it fits a 2 GB laptop

The biggest memory cost is V8 itself and the number of d8 processes running simultaneously. The fuzzer therefore uses:

1. One worker by default on roughly 2 GB systems.
2. One d8 process per testcase.
3. A bounded corpus instead of an unbounded queue.
4. 600 warm-up calls by default.
5. Small allocation pressure.
6. 48 KiB maximum testcase size.
7. A 5-second timeout.

If the laptop begins swapping:

```bash
V8_FUZZ_WORKERS=1 V8_FUZZ_WARMUP=200 V8_FUZZ_TIMEOUT=3 python3 v8_fuzzer.py
```

## Fuzzilli comparison

| Capability | This fuzzer |
|---|---|
| Structural JS generation | Yes |
| Bounded corpus | Yes |
| Lightweight mutation | Yes |
| Crash isolation | Yes |
| Timeout handling | Yes |
| JIT / GC pressure | Yes |
| Coverage feedback | **Not yet** |
| Low-memory mode | Explicit goal |

The next major architectural upgrade is **V8 coverage feedback**, allowing corpus retention to be driven by newly discovered execution edges rather than a heuristic probability.

## Crash triage

The harness watches for common native diagnostics such as AddressSanitizer, heap-use-after-free, heap-buffer-overflow, stack-buffer-overflow, SIGSEGV, SIGABRT, SIGBUS, Fatal error, DCHECK, and CHECK failures.

Saved reproducers use:

```text
crashes/crash-<timestamp>-<worker>-<sha256>.js
```

The captured stdout/stderr is appended to the reproducer.

A d8 assertion or crash is **not automatically a memory-safety vulnerability**. Reproduce it independently and root-cause it with an appropriate debug or sanitizer build.

## Repository layout

```text
V8-fuzzer/
├── v8_fuzzer.py
├── seeds/
├── corpus/       # generated automatically
├── crashes/      # generated automatically
├── README.md
└── LICENSE
```

## Responsible use

Run this project only against V8 builds and environments you are authorized to test. Do not use it to attack third-party services or systems.

## Sponsorship

**Contact:** hunterkritik@gmail.com  
See `SPONSORSHIP.md` for sponsorship, hardware-support, and collaboration information.

## Author

**Kritik Bhattarai**

V8 security research and browser-engine fuzzing.

## License

See `LICENSE`.

Copyright 2026 © Kritik Bhattarai.


## v2.2.0 — Modular fuzzing framework

This release adds reusable components modeled around a modern fuzzing pipeline:

- MutationEngine — structural mutations, boundary-value mutations, statement duplication, and corpus splicing.
- Script Runner — portable isolated d8 execution with the existing 5-second timeout.
- Corpus — persistent, bounded, content-addressed program storage.
- Minimizer — budgeted reduction that can preserve a crash/assertion predicate.
- Evaluator — portable interestingness evaluation with an optional coverage-input interface.
- Lifter — converts the small internal Program representation to JavaScript.
- Statistics — execution, timeout, crash, interestingness, minimization, and throughput counters.
- ThreadSync — process-local duplicate coordination.
- NetworkSync — optional explicit peer-to-peer corpus transfer; disabled unless used by a caller.
- Corpus runner — replay seeds/corpus without starting the full mutation campaign.

Replay a corpus directory:

    python3 run_corpus.py seeds
    python3 run_corpus.py corpus

Architecture details are documented in docs/ARCHITECTURE.md.

v2.2.0 follows the broad separation of mutation, execution, evaluation,
storage, synchronization, and minimization used by mature JavaScript fuzzers.
It remains an independent Python implementation and does not copy Fuzzilli
source code.

v8_fuzzer.py remains the primary all-in-one entry point. The new modules are
also usable independently for experiments and future coverage-provider work.

