from __future__ import annotations

import logging

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from janio_bot.config import RuntimeMode, Settings
from janio_bot.database import Database
from janio_bot.errors import JanioError
from janio_bot.services.ddragon import DataDragonClient
from janio_bot.services.metabot import MetaBotClient
from janio_bot.services.music import MusicExtractor
from janio_bot.services.riot import RiotClient

LOGGER = logging.getLogger(__name__)

BASE_EXTENSIONS = (
    "janio_bot.cogs.general",
    "janio_bot.cogs.points",
    "janio_bot.cogs.announcements",
    "janio_bot.cogs.music",
    "janio_bot.cogs.prefix",
)

MODE_EXTENSION = {
    RuntimeMode.COMMUNITY: "janio_bot.cogs.betting",
    RuntimeMode.LEAGUE: "janio_bot.cogs.league",
}


async def send_interaction_error(
    interaction: discord.Interaction, message: str
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class JanioCommandTree(app_commands.CommandTree["JanioBot"]):
    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if isinstance(original, JanioError):
            await send_interaction_error(interaction, f"❌ {original}")
            return
        if isinstance(original, app_commands.MissingPermissions):
            await send_interaction_error(
                interaction, "❌ Você não tem permissão para usar este comando."
            )
            return
        if isinstance(original, app_commands.BotMissingPermissions):
            missing = ", ".join(original.missing_permissions)
            await send_interaction_error(
                interaction, f"❌ O bot não tem as permissões necessárias: {missing}."
            )
            return
        LOGGER.exception(
            "Erro inesperado no comando %s",
            interaction.command.qualified_name if interaction.command else "?",
            exc_info=original,
        )
        await send_interaction_error(
            interaction, "❌ Ocorreu um erro inesperado. Tente novamente em instantes."
        )


class JanioBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("j!", "J!"),
            intents=intents,
            tree_cls=JanioCommandTree,
            allowed_mentions=discord.AllowedMentions.none(),
            help_command=None,
            case_insensitive=True,
        )
        self.settings = settings
        self.database = Database(
            settings.database_path,
            default_points=settings.default_points,
            daily_points=settings.daily_points,
        )
        self.web_client = httpx.AsyncClient(
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self.ddragon = DataDragonClient(
            self.web_client,
            base_url=settings.ddragon_base_url,
            locale=settings.ddragon_locale,
        )
        self.metabot = MetaBotClient(self.web_client, endpoint=settings.metabot_url)
        self.riot = RiotClient(self.web_client, settings.riot_api_key)
        self.music_extractor = MusicExtractor()

    async def setup_hook(self) -> None:
        await self.database.initialize()
        extensions = (*BASE_EXTENSIONS, MODE_EXTENSION[self.settings.mode])
        for extension in extensions:
            await self.load_extension(extension)
        LOGGER.info("Janio Bot iniciado no modo %s.", self.settings.mode.value)

        if not self.settings.sync_commands:
            LOGGER.info("Sincronização de slash commands desativada.")
            return
        if self.settings.test_guild_id is not None:
            guild = discord.Object(id=self.settings.test_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOGGER.info(
                "%d comandos sincronizados no servidor de teste %d.",
                len(synced),
                guild.id,
            )

        synced = await self.tree.sync()
        LOGGER.info("%d comandos globais sincronizados.", len(synced))

    async def on_ready(self) -> None:
        if self.user is not None:
            LOGGER.info("Janio Bot conectado como %s (%d).", self.user, self.user.id)

    async def on_command_error(
        self,
        context: commands.Context[JanioBot],  # type: ignore[override]
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        original = error.original if isinstance(error, commands.CommandInvokeError) else error
        if isinstance(original, JanioError):
            await context.send(f"❌ {original}")
            return
        if isinstance(original, commands.MissingPermissions):
            await context.send("❌ Você não tem permissão para usar este comando.")
            return
        if isinstance(original, commands.BotMissingPermissions):
            missing = ", ".join(original.missing_permissions)
            await context.send(f"❌ O bot não tem as permissões necessárias: {missing}.")
            return
        if isinstance(original, commands.NoPrivateMessage):
            await context.send("❌ Este comando precisa ser usado dentro de um servidor.")
            return
        if isinstance(
            original,
            (commands.MissingRequiredArgument, commands.BadArgument, commands.BadUnionArgument),
        ):
            detail = str(original)
            usage = (
                f"{context.clean_prefix}{context.command.qualified_name} "
                f"{context.command.signature}"
                if context.command is not None
                else f"{context.clean_prefix}ajuda"
            )
            await context.send(f"❌ {detail}\nUso: `{usage.strip()}`")
            return
        if isinstance(original, commands.CheckFailure):
            await context.send("❌ Você não pode usar este comando neste contexto.")
            return

        LOGGER.exception(
            "Erro inesperado no comando de texto %s",
            context.command.qualified_name if context.command else "?",
            exc_info=original,
        )
        await context.send("❌ Ocorreu um erro inesperado. Tente novamente em instantes.")

    async def close(self) -> None:
        await self.web_client.aclose()
        await super().close()
