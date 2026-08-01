from __future__ import annotations

from pathlib import Path

import pytest

from janio_bot.bot import JanioBot
from janio_bot.config import RuntimeMode, Settings


def settings_for(mode: RuntimeMode, database_path: Path) -> Settings:
    return Settings(
        discord_token="test-token",
        mode=mode,
        database_path=database_path,
        test_guild_id=None,
        riot_api_key=None,
        default_points=1000,
        daily_points=250,
        default_announcement_interval_seconds=210,
        default_announcement_message="Hora do palpite!",
        ffmpeg_path="ffmpeg",
        sync_commands=False,
        log_level=20,
    )


@pytest.mark.parametrize(
    ("mode", "present", "absent"),
    [
        (RuntimeMode.COMMUNITY, "aposta", "lol"),
        (RuntimeMode.LEAGUE, "lol", "aposta"),
    ],
)
async def test_runtime_mode_loads_only_its_command_group(
    tmp_path: Path,
    mode: RuntimeMode,
    present: str,
    absent: str,
) -> None:
    bot = JanioBot(settings_for(mode, tmp_path / f"{mode.value}.sqlite3"))
    try:
        await bot.setup_hook()
        commands = {command.name for command in bot.tree.get_commands()}
        assert present in commands
        assert absent not in commands
    finally:
        await bot.close()
