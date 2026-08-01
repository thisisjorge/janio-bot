from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

from janio_bot.runtime import resolve_ffmpeg_path


class ConfigurationError(ValueError):
    """Raised when environment configuration is invalid."""


class RuntimeMode(StrEnum):
    COMMUNITY = "community"
    LEAGUE = "league"


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} precisa ser um número inteiro.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} precisa ser maior que zero.")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} precisa ser um número inteiro.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} precisa ser maior que zero.")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "sim", "on"}:
        return True
    if normalized in {"0", "false", "no", "nao", "não", "off"}:
        return False
    raise ConfigurationError(f"{name} precisa ser true ou false.")


def _runtime_mode() -> RuntimeMode:
    raw = os.getenv("JANIO_MODE", RuntimeMode.COMMUNITY.value).strip().casefold()
    try:
        return RuntimeMode(raw)
    except ValueError as exc:
        choices = ", ".join(mode.value for mode in RuntimeMode)
        raise ConfigurationError(f"JANIO_MODE precisa ser uma destas opções: {choices}.") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    mode: RuntimeMode
    database_path: Path
    test_guild_id: int | None
    riot_api_key: str | None
    default_points: int
    daily_points: int
    default_announcement_interval_seconds: int
    default_announcement_message: str
    ffmpeg_path: str
    sync_commands: bool
    log_level: int
    metabot_url: str = "https://metabot.gg/api/mcp"
    ddragon_base_url: str = "https://ddragon.leagueoflegends.com"
    ddragon_locale: str = "pt_BR"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token == "cole_o_token_aqui":
            raise ConfigurationError(
                "Defina DISCORD_TOKEN no arquivo .env antes de iniciar o bot."
            )

        message = os.getenv("DEFAULT_ANNOUNCEMENT_MESSAGE", "Hora do palpite!").strip()
        if not message:
            raise ConfigurationError("DEFAULT_ANNOUNCEMENT_MESSAGE não pode ficar vazia.")

        log_level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        log_level = logging.getLevelNamesMapping().get(log_level_name)
        if not isinstance(log_level, int):
            raise ConfigurationError(f"LOG_LEVEL inválido: {log_level_name}.")

        return cls(
            discord_token=token,
            mode=_runtime_mode(),
            database_path=Path(os.getenv("DATABASE_PATH", "data/janio.sqlite3")),
            test_guild_id=_optional_int("TEST_GUILD_ID"),
            riot_api_key=os.getenv("RIOT_API_KEY", "").strip() or None,
            default_points=_positive_int("DEFAULT_POINTS", 1000),
            daily_points=_positive_int("DAILY_POINTS", 250),
            default_announcement_interval_seconds=_positive_int(
                "DEFAULT_ANNOUNCEMENT_INTERVAL_SECONDS", 210
            ),
            default_announcement_message=message,
            ffmpeg_path=resolve_ffmpeg_path(os.getenv("FFMPEG_PATH")),
            sync_commands=_boolean("SYNC_COMMANDS", True),
            log_level=log_level,
        )
