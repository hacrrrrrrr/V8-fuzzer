#!/usr/bin/env python3
"""Run a V8-Fuzzer seed/corpus directory through d8."""
from __future__ import annotations
import argparse
from pathlib import Path
from v8fuzzer.corpus_runner import CorpusRunner

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    runner = CorpusRunner()
    count = 0
    for path, evaluation in runner.run_directory(args.directory):
        count += 1
        print(f"{path}: {evaluation.reason} score={evaluation.score}", flush=True)
    print(f"completed={count}")

if __name__ == "__main__":
    main()
