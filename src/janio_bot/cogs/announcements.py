from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from janio_bot.bot import JanioBot

LOGGER = logging.getLogger(__name__)


class AnnouncementsCog(
    commands.GroupCog,
    group_name="aviso",
    group_description="Configura o aviso recorrente do servidor.",
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.announcement_worker.start()

    async def cog_unload(self) -> None:
        self.announcement_worker.cancel()

    @app_commands.command(
        name="configurar", description="Define canal, mensagem e intervalo do aviso."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Canal que receberá o aviso",
        mensagem="Texto; vazio usa a mensagem padrão",
        intervalo_segundos="210 segundos = 3 minutos e 30 segundos",
    )
    async def configure(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        intervalo_segundos: app_commands.Range[int, 30, 86_400] | None = None,
        mensagem: str | None = None,
    ) -> None:
        assert interaction.guild_id is not None
        content = mensagem or self.bot.settings.default_announcement_message
        interval = (
            intervalo_segundos
            if intervalo_segundos is not None
            else self.bot.settings.default_announcement_interval_seconds
        )
        if len(content) > 2000:
            await interaction.response.send_message(
                "A mensagem pode ter no máximo 2000 caracteres.", ephemeral=True
            )
            return
        setting = await self.bot.database.configure_announcement(
            interaction.guild_id,
            canal.id,
            content,
            interval,
        )
        await interaction.response.send_message(
            (
                f"✅ Aviso ativado em {canal.mention} a cada "
                f"**{setting.interval_seconds} segundos**.\n"
                f"Mensagem: {discord.utils.escape_markdown(setting.message)}"
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ativar", description="Ativa o aviso já configurado.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await self.bot.database.set_announcement_enabled(interaction.guild_id, True)
        await interaction.response.send_message("✅ Aviso ativado.", ephemeral=True)

    @app_commands.command(name="desativar", description="Pausa o aviso recorrente.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        await self.bot.database.set_announcement_enabled(interaction.guild_id, False)
        await interaction.response.send_message("⏸️ Aviso desativado.", ephemeral=True)

    @app_commands.command(name="status", description="Mostra a configuração do aviso.")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        setting = await self.bot.database.get_announcement(interaction.guild_id)
        if setting is None:
            await interaction.response.send_message(
                "O aviso ainda não foi configurado.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="⏰ Aviso recorrente",
            color=discord.Color.green() if setting.enabled else discord.Color.light_grey(),
        )
        embed.add_field(
            name="Estado", value="Ativado" if setting.enabled else "Desativado"
        )
        embed.add_field(name="Canal", value=f"<#{setting.channel_id}>")
        embed.add_field(name="Intervalo", value=f"{setting.interval_seconds} segundos")
        embed.add_field(name="Mensagem", value=setting.message[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="testar", description="Envia o aviso uma vez agora.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        setting = await self.bot.database.get_announcement(interaction.guild_id)
        if setting is None:
            await interaction.response.send_message(
                "Configure o aviso primeiro.", ephemeral=True
            )
            return
        channel = self.bot.get_channel(setting.channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(setting.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "O canal configurado não aceita mensagens.", ephemeral=True
            )
            return
        await channel.send(
            setting.message,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await interaction.response.send_message("✅ Aviso de teste enviado.", ephemeral=True)

    @tasks.loop(seconds=5)
    async def announcement_worker(self) -> None:
        for setting in await self.bot.database.claim_due_announcements():
            try:
                channel = self.bot.get_channel(setting.channel_id)
                if channel is None:
                    channel = await self.bot.fetch_channel(setting.channel_id)
                if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                    LOGGER.warning(
                        "Canal de aviso %d/%d não é textual.",
                        setting.guild_id,
                        setting.channel_id,
                    )
                    continue
                await channel.send(
                    setting.message,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.HTTPException, discord.Forbidden, discord.NotFound):
                LOGGER.exception(
                    "Falha ao enviar aviso do servidor %d.", setting.guild_id
                )

    @announcement_worker.before_loop
    async def before_announcement_worker(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(AnnouncementsCog(bot))
