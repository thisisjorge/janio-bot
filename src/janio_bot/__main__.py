from __future__ import annotations

import asyncio
import logging

from janio_bot.bot import JanioBot
from janio_bot.config import Settings


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(_run(settings))


async def _run(settings: Settings) -> None:
    async with JanioBot(settings) as bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    main()
