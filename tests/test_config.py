from __future__ import annotations

from pathlib import Path

import pytest

from janio_bot.config import ConfigurationError, RuntimeMode, Settings


@pytest.fixture(autouse=True)
def disable_real_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("janio_bot.config.load_dotenv", lambda: False)


def test_settings_default_to_community_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.delenv("JANIO_MODE", raising=False)
    monkeypatch.delenv("DEFAULT_ANNOUNCEMENT_MESSAGE", raising=False)

    settings = Settings.from_env()

    assert settings.mode is RuntimeMode.COMMUNITY
    assert settings.default_announcement_message == "Hora do palpite!"


def test_settings_accept_league_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("JANIO_MODE", "league")

    assert Settings.from_env().mode is RuntimeMode.LEAGUE


def test_settings_reject_unknown_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("JANIO_MODE", "todos")

    with pytest.raises(ConfigurationError, match="JANIO_MODE"):
        Settings.from_env()
