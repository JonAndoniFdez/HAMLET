from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return Windows-only flags that keep console child processes hidden."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def run_hidden(*popenargs, **kwargs) -> subprocess.CompletedProcess:
    for key, value in hidden_subprocess_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.run(*popenargs, **kwargs)


def popen_hidden(*popenargs, **kwargs) -> subprocess.Popen:
    for key, value in hidden_subprocess_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.Popen(*popenargs, **kwargs)
