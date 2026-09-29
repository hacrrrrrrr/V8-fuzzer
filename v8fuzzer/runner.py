"""Portable d8 script runner."""

from __future__ import annotations

import os
import signal
import subprocess


class D8Runner:
    def __init__(self, d8_path="./d8", flags=("--fuzzing", "--expose-gc",
                 "--allow-natives-syntax"), timeout=5.0):
        self.d8_path = d8_path
        self.flags = tuple(flags)
        self.timeout = timeout

    def _kwargs(self):
        if os.name == "nt":
            return {"creationflags": getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        return {"start_new_session": True}

    def _kill_tree(self, proc):
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def run(self, source: str):
        proc = subprocess.Popen(
            (self.d8_path, *self.flags, "-"), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            errors="replace", **self._kwargs())
        try:
            out, err = proc.communicate(source, timeout=self.timeout)
            timeout = False
        except subprocess.TimeoutExpired:
            timeout = True
            self._kill_tree(proc)
            out, err = proc.communicate()
        return {
            "stdout": out,
            "stderr": err,
            "returncode": proc.returncode,
            "timeout": timeout,
        }
