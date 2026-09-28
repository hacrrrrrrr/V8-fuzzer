# Corpus

The corpus is intentionally organized by behavior instead of by claimed vulnerability.

- `core/` — language/runtime fundamentals
- `jit/` — warm-up and optimization stress
- `memory/` — allocation, GC, ArrayBuffer, TypedArray and lifetime patterns
- `intl/` — ECMA-402 and ICU/calendar paths
- `boundaries/` — index/length/representation boundary cases
- `regressions/` — minimized historical reproducers
- `crashes/` — locally discovered crashes after triage

Do not label a testcase as UAF/OOB/type-confusion merely because its input resembles a known bug. Keep the classification evidence-based.
