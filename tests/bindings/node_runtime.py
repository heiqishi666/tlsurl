"""Resolve launcher shims before owning a Node subprocess lifecycle."""
from functools import cache
from pathlib import Path
import subprocess


@cache
def node_executable():
    executable = subprocess.check_output(
        ["node", "-p", "process.execPath"], text=True, timeout=15
    ).strip()
    if not Path(executable).is_file():
        raise RuntimeError(f"Node executable does not exist: {executable}")
    return executable
