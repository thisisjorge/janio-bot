from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from janio_bot import runtime


def _unexpected_import(name: str) -> None:
    raise AssertionError(f"unexpected import: {name}")


def test_resolve_ffmpeg_respects_explicit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "janio_bot.runtime.shutil.which", lambda _: pytest.fail("PATH was searched")
    )

    assert runtime.resolve_ffmpeg_path("  /custom/ffmpeg  ") == "/custom/ffmpeg"


def test_resolve_ffmpeg_uses_path_before_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("janio_bot.runtime.shutil.which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", _unexpected_import)

    assert runtime.resolve_ffmpeg_path() == "/usr/bin/ffmpeg"


def test_resolve_ffmpeg_uses_imageio_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("janio_bot.runtime.shutil.which", lambda _: None)
    module = SimpleNamespace(get_ffmpeg_exe=lambda: " /bundle/ffmpeg ")
    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", lambda _: module)

    assert runtime.resolve_ffmpeg_path() == "/bundle/ffmpeg"


def test_resolve_ffmpeg_keeps_command_when_package_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("janio_bot.runtime.shutil.which", lambda _: None)

    def missing(_: str) -> None:
        raise ModuleNotFoundError

    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", missing)

    assert runtime.resolve_ffmpeg_path() == "ffmpeg"


def test_existing_javascript_runtime_is_used_without_path_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path = os.pathsep.join(("first", "second"))
    monkeypatch.setenv("PATH", original_path)
    monkeypatch.setattr(
        "janio_bot.runtime.shutil.which",
        lambda executable: "/usr/bin/node" if executable == "node" else None,
    )
    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", _unexpected_import)

    assert runtime.ensure_javascript_runtime() == "/usr/bin/node"
    assert os.environ["PATH"] == original_path


def test_packaged_deno_directory_is_prepended_to_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deno_path = tmp_path / "package" / "deno"
    monkeypatch.setenv("PATH", os.pathsep.join(("first", "second")))
    monkeypatch.setattr("janio_bot.runtime.shutil.which", lambda _: None)
    module = SimpleNamespace(find_deno_bin=lambda: str(deno_path))
    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", lambda _: module)

    assert runtime.ensure_javascript_runtime() == str(deno_path)
    assert os.environ["PATH"].split(os.pathsep) == [
        str(deno_path.parent.resolve()),
        "first",
        "second",
    ]


def test_missing_packaged_deno_leaves_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "original")
    monkeypatch.setattr("janio_bot.runtime.shutil.which", lambda _: None)

    def missing(_: str) -> None:
        raise ModuleNotFoundError

    monkeypatch.setattr("janio_bot.runtime.importlib.import_module", missing)

    assert runtime.ensure_javascript_runtime() is None
    assert os.environ["PATH"] == "original"
