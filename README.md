# V8 Fuzzer — Lightweight, Fuzzilli-Inspired d8 Fuzzing

**A small-footprint V8 JavaScript engine fuzzer for authorized local security research.**

> Built for practical fuzzing on ordinary hardware, including laptops with around **2 GB RAM**.

This project uses ideas common to modern JavaScript fuzzers: corpus-based generation, mutation, program diversity, crash isolation, and continuous testcase execution. It is **not a reimplementation of Fuzzilli** and currently does not provide engine coverage feedback.

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

## Author

**Kritik Bhattarai**

V8 security research and browser-engine fuzzing.

## License

See `LICENSE`.

Copyright 2026 © Kritik Bhattarai.


## Fuzzilli-style architecture

The current implementation has been moved from a simple random testcase loop toward a modular fuzzer architecture:

```text
                    ┌─────────────────────────┐
                    │       Program Pool      │
                    │ seeds + persistent      │
                    │ corpus                  │
                    └────────────┬────────────┘
                                 │
                       choose / generate
                                 │
                ┌────────────────▼────────────────┐
                │        Program Mutator          │
                │ literal / loop / GC / splice    │
                └────────────────┬────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    d8 Execution         │
                    │ fuzzing + GC + natives  │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┼────────────────┐
                 │               │                │
              timeout           crash           normal
                 │               │                │
                 ▼               ▼                ▼
              discard       signature +       corpus
                             reducer            candidate
                                 │
                                 ▼
                         minimized reproducer
```

The important difference from the previous version is that generation and mutation are now separate concepts. A generated program becomes a reusable corpus input, and future programs can be produced by mutating or splicing existing programs.

### Components

- **Program generator** — creates structured JavaScript from target families, setup templates, conversion callbacks and boundary values.
- **Mutator** — applies several small mutations rather than replacing the whole testcase with random text.
- **Corpus** — persistent, bounded program database stored under `corpus/`.
- **Executor** — runs each testcase in an isolated `d8` process.
- **Crash signature** — groups common native failures using diagnostic signatures.
- **Reducer** — performs a lightweight line-chunk reduction while preserving the crash signature.
- **Memory scheduler** — limits the number of concurrent d8 processes according to available RAM.

### The path toward real coverage guidance

The architecture is deliberately split so a native V8 coverage provider can be added later:

```text
                    Program
                       │
                       ▼
                 d8 + coverage
                       │
                       ▼
             edge / feature bitmap
                       │
              new feature?
                 ┌─────┴─────┐
                no          yes
                 │            │
              discard      retain
                              │
                              ▼
                           mutate
```

At the moment, the repository uses heuristic corpus retention rather than claiming to have Fuzzilli's native coverage feedback. Adding actual V8 edge coverage is the next major step required for a closer functional match.

### Why not claim "same as Fuzzilli"?

Fuzzilli is a mature coverage-guided JavaScript fuzzer with a substantially richer program representation, mutation system, engine integration and feedback infrastructure. This repository now follows similar **architectural ideas** while remaining a small Python/d8 implementation that can operate on a low-memory laptop.

The goal is compatibility of the workflow, not copying Fuzzilli's implementation.


## Intl / Persian-calendar fuzzing

The generator now includes ECMA-402 date/time paths using the Persian calendar, including:

- `fa-IR-u-ca-persian`
- `calendar: "persian"`
- `numberingSystem: "arabext"`
- `Intl.DateTimeFormat.prototype.format`
- `formatRange`
- `resolvedOptions()`
- date values spanning epoch, negative timestamps, large timestamps, and year-2038-adjacent values

This is intended to exercise V8's JavaScript-to-ICU/ECMA-402 boundary and date/calendar option handling.

A calendar-related crash is **not automatically a UAF**. The fuzzer records native crash diagnostics; a suspected use-after-free should be confirmed with an ASan/UBSan build and a minimized reproducer. The fuzzer does not assume a vulnerability class from the symptom alone.
