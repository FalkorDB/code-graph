"""Bench-only LocalEnvironment that kills the whole process group on timeout.

Why this file exists
--------------------

``minisweagent.environments.local.LocalEnvironment.execute`` calls
``subprocess.run(shell=True, timeout=N)``. On timeout, Python sends
SIGKILL to the immediate shell PID — but any child the agent spawned
inside that shell (e.g. ``bash -c 'python -c "from sympy import ..."'``)
becomes orphaned and reparented to PID 1. We caught four such orphans
in the n=10 Opus run, each pegged at ~100% CPU for **3-4 hours**
after the parent trajectory had long since exited — all
``python -c "from sympy import *; factor(..., extension=[I])"``
snippets the agent had run to reproduce the very infinite-loop bug it
was trying to fix in sympy-19040.

Fix: spawn each command via ``Popen(start_new_session=True)`` so it
gets its own process group, then on timeout ``os.killpg(pgid,
SIGKILL)`` so every descendant dies. Output / returncode handling is
otherwise identical to upstream so trajectories remain comparable.
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
from typing import Any

from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
from minisweagent.exceptions import Submitted
from minisweagent.utils.serialize import recursive_merge


class SafeLocalEnvironment(LocalEnvironment):
    """LocalEnvironment that SIGKILLs the whole process group on timeout."""

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        command = action.get("command", "")
        cwd = cwd or self.config.cwd or os.getcwd()
        effective_timeout = timeout or self.config.timeout

        proc = subprocess.Popen(
            command,
            shell=True,
            text=True,
            cwd=cwd,
            env=os.environ | self.config.env,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Put the shell — and every descendant — in its own process
            # group so we can SIGKILL the whole tree on timeout.
            start_new_session=True,
        )

        try:
            stdout, _ = proc.communicate(timeout=effective_timeout)
            output = {
                "output": stdout or "",
                "returncode": proc.returncode,
                "exception_info": "",
            }
        except subprocess.TimeoutExpired as e:
            # The shell ignored its deadline (or the agent's command
            # double-forked). Kill the *group* so orphaned children
            # (e.g. `python -c "from sympy import ..."`) die too.
            self._kill_process_group(proc.pid)
            try:
                stdout, _ = proc.communicate(timeout=5)
            except Exception:
                stdout = ""
            raw = e.output or stdout or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            output = {
                "output": raw,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {
                    "exception_type": type(e).__name__,
                    "exception": str(e),
                    "killed_process_group": True,
                },
            }
        except Exception as e:
            # Best-effort: still try to kill anything we spawned.
            try:
                self._kill_process_group(proc.pid)
            except Exception:
                pass
            raw = getattr(e, "output", None) or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            output = {
                "output": raw,
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }

        self._check_finished(output)
        return output

    @staticmethod
    def _kill_process_group(pid: int) -> None:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                return
            except PermissionError:
                return
            # Give SIGTERM a brief moment before escalating to SIGKILL.
            if sig is signal.SIGTERM:
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass


__all__ = ["SafeLocalEnvironment", "LocalEnvironmentConfig"]
