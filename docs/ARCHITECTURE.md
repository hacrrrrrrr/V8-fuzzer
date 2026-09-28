# V8-Fuzzer Architecture

V8-Fuzzer is a lightweight, corpus-driven JavaScript engine fuzzing framework designed for local V8/d8 research.

## Pipeline

```text
Seeds → Generator → Mutators → d8 → Crash/Timeout/Novelty
  ↑                         │
  └──── Corpus ← Reducer ←─┘
```

The project is inspired by the architecture of coverage-guided JavaScript fuzzers such as Fuzzilli, while remaining an independent implementation. Fuzzilli uses an intermediate language, mutation engines, corpus management, minimization, and coverage evaluation; see the upstream documentation for the conceptual model. 

## Bug-pattern families

- bounds and indexed access
- representation/type transitions
- object-shape transitions
- prototype mutation
- callback re-entry
- GC/lifetime pressure
- TypedArray/DataView/ArrayBuffer boundaries
- strings and Intl/ICU
- WebAssembly boundary cases
- JIT warm-up and optimization stress
- assertion/invariant stress

A crash signature is treated as evidence for investigation, not as proof of a particular vulnerability class.
