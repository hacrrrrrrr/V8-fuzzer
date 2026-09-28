# V8 Structural Mutation Fuzzer

**V8 / d8 security-oriented mutation fuzzer** for authorized local testing of V8 builds.

> **Made by Kritik Bhattarai**

This project focuses on exercising JavaScript-to-native conversion boundaries where
user-controlled JavaScript callbacks can execute during coercion, while V8 is under
GC pressure and JIT optimization.

## Features

- Multi-process fuzzing using Python 3 `multiprocessing`
- One isolated `d8` process per testcase
- Automatic worker count based on available CPU cores
- Fresh randomized testcase generation
- JIT warm-up before conversion triggers
- Explicit GC and allocation pressure
- Heap fragmentation patterns using ArrayBuffers and arrays
- Object-shape and property deletion/addition churn
- `valueOf()`, `toString()`, and `Symbol.toPrimitive` callouts
- Array, String, and TypedArray target operations
- Integer and floating-point boundary values
- 2.5-second per-process timeout
- Crash detection using exit status and native diagnostic markers
- Automatic preservation of reproducing JavaScript cases
- Captured stdout/stderr stored directly with crash reproducers
- Standalone seed cases for deterministic starting points
- No third-party Python dependencies

## Repository Layout

```text
V8-fuzzer/
├── v8_fuzzer.py
├── seeds/
│   └── conversion_gc_boundary.js
├── crashes/
│   └── generated automatically
├── README.md
└── LICENSE
```

## Target Harness

The fuzzer launches:

```text
./d8 --fuzzing --expose-gc --trace-gc --stress-compaction --stress-compaction-random --predictable
```

The target binary is intentionally configured as:

```python
D8_PATH = "./d8"
```

## Architecture

### 1. Testcase Generation

Every iteration constructs a new JavaScript program from several independently
randomized dimensions:

```text
             ┌─────────────────────┐
             │ Randomized generator│
             └──────────┬──────────┘
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
  Target API       Conversion hook    Edge values
       │                │                │
       └────────────────┼────────────────┘
                        ▼
                GC / heap pressure
                        │
                        ▼
                  JIT warm-up
                        │
                        ▼
                 d8 testcase
```

The generator deliberately combines components rather than relying on random
JavaScript syntax. This produces syntactically valid programs that repeatedly
exercise high-value engine boundaries.

### 2. Conversion Boundaries

Generated objects can implement:

- `valueOf()`
- `toString()`
- `Symbol.toPrimitive`

Those callbacks perform allocations, object-shape mutations, and explicit GC
before returning a value to the builtin conversion path.

This is useful for testing situations where native engine code crosses back
into JavaScript and execution can trigger allocation or garbage collection.

### 3. JIT Pressure

The fuzzer warms selected target functions with approximately 2,200 calls before
introducing the conversion object.

This is intended to increase coverage of optimized execution paths while still
allowing the same operation to be executed with different argument types.

### 4. Heap Pressure

The generator creates alternating ArrayBuffers and arrays, releases selected
references, mutates object properties, and invokes `gc()` where available.

The goal is to exercise object lifetime and representation transitions rather
than merely maximize allocation volume.

## Current Target Families

The generator currently includes variants around:

- `Array.prototype.fill`
- `Array.prototype.lastIndexOf`
- `String.prototype.charAt`
- TypedArray construction and slicing
- `TypedArray.prototype.set`
- `Array.prototype.copyWithin`
- `Array.prototype.includes`
- `Array.prototype.indexOf`

The target list is intentionally easy to extend in `TARGETS`.

## Running

Place the V8 `d8` binary in the repository root:

```text
./d8
```

Then:

```bash
python3 v8_fuzzer.py
```

A normal startup looks like:

```text
[+] V8 d8 fuzzer: workers=16, timeout=2.5s
[+] target: ./d8
```

The fuzzer continues until interrupted when:

```python
ITERATIONS_PER_WORKER = 0
```

is used.

For a bounded campaign, set for example:

```python
ITERATIONS_PER_WORKER = 1000
```

## Configuration

The main configuration is at the top of `v8_fuzzer.py`:

| Setting | Purpose |
|---|---|
| `D8_PATH` | Path to the V8 shell |
| `WORKERS` | Number of independent fuzzing processes |
| `TIMEOUT_SECONDS` | Maximum execution time per testcase |
| `ITERATIONS_PER_WORKER` | Number of cases per worker; 0 = unlimited |
| `WARMUP_ITERS` | JIT warm-up iterations |
| `CRASH_DIR` | Crash-reproducer directory |

## Crash Triage

A testcase is recorded when the d8 process reports a crash-like termination
or diagnostic text associated with native memory-safety failures and fatal
engine assertions.

Examples of monitored diagnostics include:

```text
AddressSanitizer
heap-use-after-free
heap-buffer-overflow
stack-buffer-overflow
Segmentation fault
SIGSEGV
Fatal error
DCHECK
CHECK failed
ASSERT
```

Saved reproducers have the form:

```text
crashes/crash-<timestamp>-<worker>-<sha256>.js
```

The JavaScript testcase is followed by a block comment containing the captured
stdout/stderr diagnostics.

This makes each crash artifact directly useful for reproduction and subsequent
manual reduction.

## Standalone Seed

A hand-written seed is included at:

```text
seeds/conversion_gc_boundary.js
```

It exercises a conversion callback while combining:

- JIT warm-up
- object-shape mutation
- allocation pressure
- garbage collection
- `Array.prototype.fill`

It can be executed directly:

```bash
./d8 --fuzzing --expose-gc --stress-compaction --stress-compaction-random --predictable seeds/conversion_gc_boundary.js
```

## Recommended V8 Builds

For vulnerability triage, use a V8 build appropriate for the bug class being
investigated. Sanitizer-enabled builds can provide substantially better
diagnostics for native memory-safety failures.

The fuzzer itself does not require a special Python environment.

## Responsible Use

Run this project only against V8 builds and environments you are authorized to
test. Do not use it to attack third-party services or systems.

This repository is a research and testing tool. A testcase that triggers an
assertion is not automatically evidence of a memory-safety vulnerability;
crashes should be independently reproduced and root-caused.

## Author

**Kritik Bhattarai**

V8 security research and browser-engine fuzzing.

## License

This repository is distributed under the license included in
[`LICENSE`](LICENSE).

Copyright © Kritik Bhattarai.

---

**Made by Kritik Bhattarai**
