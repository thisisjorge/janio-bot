from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.config import RuntimeMode
from janio_bot.ui import make_embed, Colors


class GeneralCog(commands.Cog):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Mostra a latência do Janio Bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            embed=make_embed(title="🏓 Pong!", description=f"Latência da API: `{latency} ms`", color=Colors.INFO),
            ephemeral=True
        )

    @app_commands.command(name="janio", description="Mostra os recursos e comandos do bot.")
    async def janio(self, interaction: discord.Interaction) -> None:
        community_mode = self.bot.settings.mode is RuntimeMode.COMMUNITY
        embed = make_embed(
            title="🤖 Janio Bot",
            description=(
                "Pontos e previsões da comunidade, música e aviso recorrente."
                if community_mode
                else "Dados de League of Legends, música e aviso recorrente."
            ),
        )
        if community_mode:
            embed.add_field(
                name="🎯 Previsões",
                value="`/aposta criar`, `/aposta apostar`, `/aposta abertas`",
                inline=False,
            )
        embed.add_field(
            name="🪙 Pontos",
            value="`/pontos saldo`, `/pontos diario`, `/pontos ranking`",
            inline=False,
        )
        if not community_mode:
            embed.add_field(
                name="⚔️ League",
                value="`/lol build`, `/lol runas`, `/lol jogador`",
                inline=False,
            )
        embed.add_field(
            name="🎵 Música e aviso",
            value="`/musica tocar`, `/musica fila`, `/aviso configurar`",
            inline=False,
        )
        embed.set_footer(
            text="Pontos são virtuais: não podem ser comprados, sacados ou trocados."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(GeneralCog(bot))
