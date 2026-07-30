"""Trusted local execution primitives for worker operations."""
from .subprocess_runner import CommandResult, run_argv, run_stdin

__all__ = ["CommandResult", "run_argv", "run_stdin"]
