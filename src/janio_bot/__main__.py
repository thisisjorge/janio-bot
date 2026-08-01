from __future__ import annotations

import asyncio
import logging

from janio_bot.config import Settings
from janio_bot.runtime import ensure_javascript_runtime

LOGGER = logging.getLogger(__name__)


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    LOGGER.info("FFmpeg disponivel em %s.", settings.ffmpeg_path)
    javascript_runtime = ensure_javascript_runtime()
    if javascript_runtime is None:
        LOGGER.warning(
            "Nenhum runtime JavaScript foi encontrado; algumas fontes de musica podem falhar."
        )
    else:
        LOGGER.info("Runtime JavaScript disponivel em %s.", javascript_runtime)
    asyncio.run(_run(settings))


async def _run(settings: Settings) -> None:
    # Import after runtime discovery so yt-dlp sees a packaged Deno binary when needed.
    from janio_bot.bot import JanioBot

    async with JanioBot(settings) as bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    main()
