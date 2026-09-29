## v2.3.0 — Feedback and triage helpers — 2026-09-29

- Added `v8fuzzer.advanced_feedback.FeatureFeedback` for deterministic heuristic corpus retention based on stress-feature combinations.
- Added `CrashDeduplicator` for atomic cross-worker crash-signature claiming.
- Added `TimeoutStore` for bounded persistence of hangs/timeouts instead of silently discarding them.
- Kept the helpers dependency-free and usable by the existing all-in-one fuzzer or modular runner.

# Changelog

## v2.2.0 — Modular fuzzing framework — 2026-09-29

- Added a reusable MutationEngine for boundary mutation, statement duplication, and corpus splicing.
- Added a standalone d8 Script Runner and `run_corpus.py` for seed/corpus replay.
- Added Evaluator support for portable interestingness and optional coverage input.
- Added a reusable Minimizer component for budgeted reduction.
- Added a Lifter abstraction for translating program fragments to JavaScript.
- Added content-addressed Storage for corpus and diagnostic artifacts.
- Added Statistics counters for executions, timeouts, crashes, interesting samples, minimizations, and throughput.
- Added ThreadSync and opt-in NetworkSync components.
- Added modular architecture documentation.



## v2.1.0 — Issue #1 improvement release — 2026-09-29

- Added explicit `Issue #1` tracking in the fuzzer and release documentation.
- Added reproducible campaign seeds through `V8_FUZZ_SEED`.
- Added configurable crash minimization through `V8_FUZZ_MINIMIZE`.
- Added configurable minimization budget through `V8_FUZZ_MINIMIZE_BUDGET`.
- Keeps the original crash artifact even when minimization is enabled.
- Reports the tracked issue and minimization configuration at startup.



## v2.0.0 — 2026-09-28

### Cross-platform release

- Added explicit project versioning.
- Added platform detection for Linux, macOS, and Windows.
- Added Windows available-RAM detection through the standard Windows API.
- Added macOS RAM fallback using `sysctl`.
- Added Windows process-tree termination using `taskkill /T /F`.
- Kept POSIX process-group termination for Linux/macOS.
- Added Windows `d8.exe` resolution while retaining the configured default `./d8`.
- Added platform and architecture information to startup diagnostics.
- Preserved the requested d8 flags:
  - `--fuzzing`
  - `--expose-gc`
  - `--allow-natives-syntax`
- Preserved the 5-second testcase timeout.
- Kept worker count configurable through `V8_FUZZ_WORKERS`.
- Kept the implementation dependency-free.

### Compatibility

The Python harness is intended to run on common Python 3 environments on:

- Linux x86_64 / ARM64
- macOS x86_64 / Apple Silicon
- Windows x86_64 / ARM64

The availability of `d8` itself depends on the V8 build you provide for the
target operating system and architecture.

### Important

“Cross-platform” refers to the Python harness and process-management layer.
It does not mean one `d8` binary runs unchanged on every CPU or operating
system.
