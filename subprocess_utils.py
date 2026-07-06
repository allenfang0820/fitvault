"""Small subprocess helpers shared by backend providers.

The helpers keep command arguments as arrays and hide Windows console windows
for background child processes. They intentionally do not resolve executable
paths or alter provider-specific behavior.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Sequence


def _validate_args(args: Sequence[Any]) -> Sequence[Any]:
    if isinstance(args, (str, bytes, os.PathLike)):
        raise TypeError("subprocess args must be a list or tuple, not a shell string")
    if not isinstance(args, (list, tuple)):
        raise TypeError("subprocess args must be a list or tuple")
    return args


def windows_hidden_startup_kwargs(extra_creationflags: int = 0, **existing: Any) -> dict[str, Any]:
    kwargs = dict(existing)
    if os.name != "nt":
        return kwargs

    creationflags = int(kwargs.pop("creationflags", 0) or 0)
    create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    merged_flags = creationflags | create_no_window | int(extra_creationflags or 0)
    if merged_flags:
        kwargs["creationflags"] = merged_flags

    if kwargs.get("startupinfo") is None:
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_cls is not None:
            startupinfo = startupinfo_cls()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = startupinfo

    return kwargs


def _prepare_kwargs(kwargs: dict[str, Any], extra_creationflags: int = 0) -> dict[str, Any]:
    if kwargs.get("shell") is True:
        raise ValueError("run_hidden/popen_hidden require shell=False")
    kwargs["shell"] = False
    return windows_hidden_startup_kwargs(extra_creationflags=extra_creationflags, **kwargs)


def run_hidden(args: Sequence[Any], **kwargs: Any) -> subprocess.CompletedProcess:
    command = _validate_args(args)
    extra_creationflags = int(kwargs.pop("extra_creationflags", 0) or 0)
    return subprocess.run(command, **_prepare_kwargs(kwargs, extra_creationflags))


def popen_hidden(args: Sequence[Any], **kwargs: Any) -> subprocess.Popen:
    command = _validate_args(args)
    extra_creationflags = int(kwargs.pop("extra_creationflags", 0) or 0)
    return subprocess.Popen(command, **_prepare_kwargs(kwargs, extra_creationflags))
