"""Non-shell subprocess execution with structured, redacted results."""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _argv(argv: Sequence[str]) -> list[str]:
    values = [str(value) for value in argv]
    if not values or any("\x00" in value for value in values):
        raise ValueError("argv must be non-empty and contain no NUL bytes")
    return values


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def run_argv(argv: Sequence[str], *, cwd: str | None = None, timeout: float = 60) -> CommandResult:
    values = _argv(argv)
    try:
        proc = subprocess.run(values, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, values, None, _text(exc.stdout), _text(exc.stderr), True)
    return CommandResult(proc.returncode == 0, values, proc.returncode, proc.stdout, proc.stderr)


def run_stdin(argv: Sequence[str], input_text: str, *, cwd: str | None = None, timeout: float = 60) -> CommandResult:
    values = _argv(argv)
    if not isinstance(input_text, str):
        raise TypeError("input_text must be a string")
    try:
        proc = subprocess.run(values, cwd=cwd, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(False, values, None, _text(exc.stdout), _text(exc.stderr), True)
    return CommandResult(proc.returncode == 0, values, proc.returncode, proc.stdout, proc.stderr)
