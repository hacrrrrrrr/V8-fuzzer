# Crash Triage

The fuzzer records native failures including ASan/UBSan diagnostics, CHECK/DCHECK/FATAL messages, SIGSEGV, SIGABRT, and SIGBUS.

## Workflow

1. Preserve the original testcase and stderr.
2. Group by crash signature.
3. Re-run the testcase against the same d8 build.
4. Reproduce with a debug or sanitizer build.
5. Minimize while preserving the same failure.
6. Determine the root cause from the stack and source.
7. Only then classify it as OOB, UAF, type confusion, integer overflow, assertion failure, etc.

A CHECK/DCHECK/FATAL or SIGSEGV is not itself evidence of memory corruption.
