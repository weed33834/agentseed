"""AgentSeed deterministic execution channel.

Runs a command (no shell) in a subprocess with timeout and captured output.
Turns "tests pass" into an observed fact.
"""

from __future__ import annotations

import subprocess


def sandbox_run(command: list[str], timeout: int = 30, cwd: str | None = None) -> dict:
    """Run a command as a subprocess (no shell) with a timeout.

    Deterministic verification channel: turns "the test passes" into an
    observed fact (exit code + output). No shell means no injection via args;
    output is truncated to keep the tool response bounded.

    Returns:
        {"exit_code": int, "stdout": str, "stderr": str, "timed_out": bool}
    """
    if not isinstance(command, list) or not command:
        return {"exit_code": -3, "stdout": "", "stderr": "command must be a non-empty list", "timed_out": False}
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 120)),
            cwd=cwd,
            check=False,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-4000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout}s", "timed_out": True}
    except FileNotFoundError as exc:
        return {"exit_code": -2, "stdout": "", "stderr": f"command not found: {exc}", "timed_out": False}
    except Exception as exc:  # noqa: BLE001
        return {"exit_code": -9, "stdout": "", "stderr": f"run failed: {exc}", "timed_out": False}