# V8-Fuzzer Architecture

V8-Fuzzer is a lightweight, corpus-driven JavaScript engine fuzzing framework designed for local V8/d8 research.

## Pipeline

    Seed corpus -> MutationEngine -> Lifter -> d8 Runner -> Evaluator
                         |                 |             |
                         |                 v             v
                         +-----------> Statistics    Corpus/Storage
                                                        |
                                                        v
                                                    Minimizer

The architecture is inspired by production JavaScript fuzzers such as Fuzzilli, while remaining an independent implementation. It does not copy Fuzzilli source code.

## Components

### MutationEngine
v8fuzzer.mutation.MutationEngine performs boundary-value mutation, loop mutation, statement duplication, and corpus splicing.

### Script runner
v8fuzzer.runner.D8Runner runs a single JavaScript sample in an isolated d8 process with the project's default flags and timeout.

run_corpus.py provides deterministic seed/corpus replay.

### Corpus and Storage
v8fuzzer.storage.Storage stores programs using content-addressed filenames, avoiding duplicate artifacts.

### Minimizer
v8fuzzer.minimizer.Minimizer performs budgeted line-level delta reduction. The caller supplies the predicate, so the same reducer can preserve a crash, assertion, or another interesting behavior.

### Evaluator
v8fuzzer.evaluator.Evaluator computes portable interestingness from execution diagnostics, exit status, source features, and optional coverage text.

Actual V8 edge coverage is deliberately an optional provider: the framework does not pretend that a normal d8 build provides coverage merely because the fuzzer has an evaluator.

### Lifter
v8fuzzer.lifter.Lifter converts the small internal Program representation to JavaScript.

### Statistics
v8fuzzer.statistics.Statistics tracks executions, timeouts, crashes, interesting samples, minimizations, and execution throughput.

### ThreadSync
ThreadSync provides process-local duplicate claims for cooperating workers.

### NetworkSync
NetworkSync is opt-in. It sends explicitly supplied corpus data to a configured peer and does not create a listener or contact a service by default.

## Design goal

The framework separates generation, mutation, execution, evaluation, storage, and reduction so individual components can be replaced with stronger feedback providers later without rewriting the whole fuzzer.
