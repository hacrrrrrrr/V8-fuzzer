# V8-fuzzer

A dependency-free Python 3 mutation fuzzer for local testing of V8's d8 shell.

## Run

Build a V8 d8 binary and place it at:

```
./d8
```

Then run:

```
python3 v8_fuzzer.py
```

The default harness uses:

```
./d8 --fuzzing --expose-gc --trace-gc --stress-compaction --stress-compaction-random --predictable
```

The fuzzer uses one independent d8 process per worker, with a 2.5 second
per-case timeout. Generated programs exercise conversion callbacks,
allocation/GC pressure, object-shape transitions, JIT warm-up, and several
Array/String/TypedArray conversion paths.

Crashes are written to crashes/ with the exact JavaScript input followed by
a block comment containing stdout/stderr diagnostics.

This is intended for local V8 security research against builds you are
authorized to test. Sanitizer-enabled V8 builds are recommended for triage.

## Configuration

Edit the constants at the top of v8_fuzzer.py:

- D8_PATH
- WORKERS
- TIMEOUT_SECONDS
- ITERATIONS_PER_WORKER
- WARMUP_ITERS

ITERATIONS_PER_WORKER = 0 means run until interrupted.
