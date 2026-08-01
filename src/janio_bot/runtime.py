from __future__ import annotations

import importlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

JAVASCRIPT_RUNTIME_EXECUTABLES = ("deno", "node", "bun", "qjs")


def resolve_ffmpeg_path(explicit_path: str | None = None) -> str:
    """Resolve FFmpeg without overriding an explicit operator configuration."""
    if explicit_path is not None and (configured := explicit_path.strip()):
        return configured

    if system_ffmpeg := shutil.which("ffmpeg"):
        return system_ffmpeg

    try:
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        get_ffmpeg_exe = cast(Callable[[], str], imageio_ffmpeg.get_ffmpeg_exe)
        bundled_ffmpeg = get_ffmpeg_exe().strip()
    except (ImportError, AttributeError, OSError, RuntimeError):
        return "ffmpeg"

    return bundled_ffmpeg or "ffmpeg"


def ensure_javascript_runtime() -> str | None:
    """Expose packaged Deno on PATH only when no supported JS runtime is available."""
    for executable in JAVASCRIPT_RUNTIME_EXECUTABLES:
        if runtime_path := shutil.which(executable):
            return runtime_path

    try:
        deno = importlib.import_module("deno")
        find_deno_bin = cast(Callable[[], str], deno.find_deno_bin)
        deno_path = find_deno_bin().strip()
    except (ImportError, AttributeError, OSError, RuntimeError):
        return None

    if not deno_path:
        return None

    deno_directory = str(Path(deno_path).expanduser().resolve().parent)
    current_path = os.environ.get("PATH", "")
    path_entries = [entry for entry in current_path.split(os.pathsep) if entry]
    normalized_entries = {os.path.normcase(os.path.abspath(entry)) for entry in path_entries}
    if os.path.normcase(os.path.abspath(deno_directory)) not in normalized_entries:
        os.environ["PATH"] = os.pathsep.join((deno_directory, *path_entries))

    return deno_path
