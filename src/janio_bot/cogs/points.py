from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.errors import DailyAlreadyClaimed


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"


class PointsCog(
    commands.GroupCog,
    group_name="pontos",
    group_description="Saldo e pontos virtuais do servidor.",
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    @app_commands.command(name="saldo", description="Mostra o saldo de pontos.")
    @app_commands.guild_only()
    async def balance(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ) -> None:
        assert interaction.guild_id is not None
        target = membro or interaction.user
        balance = await self.bot.database.get_balance(interaction.guild_id, target.id)
        await interaction.response.send_message(
            f"🪙 **{target.display_name}** tem **{balance:,} pontos**.".replace(",", ".")
        )

    @app_commands.command(
        name="diario", description="Resgata o bônus diário de pontos virtuais."
    )
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        try:
            new_balance = await self.bot.database.claim_daily(
                interaction.guild_id, interaction.user.id
            )
        except DailyAlreadyClaimed as exc:
            await interaction.response.send_message(
                f"⏳ Volte em **{_format_duration(exc.retry_after_seconds)}**.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            (
                f"🎁 Você recebeu **{self.bot.settings.daily_points} pontos**. "
                f"Saldo: **{new_balance:,}**."
            ).replace(",", ".")
        )

    @app_commands.command(name="ranking", description="Mostra os maiores saldos do servidor.")
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        entries = await self.bot.database.leaderboard(interaction.guild_id)
        if not entries:
            await interaction.response.send_message(
                "Ainda não há ninguém no ranking.", ephemeral=True
            )
            return
        guild = interaction.guild
        assert guild is not None
        medals = ("🥇", "🥈", "🥉")
        lines = []
        for index, entry in enumerate(entries):
            member = guild.get_member(entry.user_id)
            name = member.display_name if member is not None else f"Usuário {entry.user_id}"
            prefix = medals[index] if index < len(medals) else f"`{index + 1}.`"
            lines.append(
                f"{prefix} **{discord.utils.escape_markdown(name)}** — "
                f"{entry.balance:,} pontos".replace(",", ".")
            )
        embed = discord.Embed(
            title="🏆 Ranking de pontos",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="dar", description="Adiciona pontos ao saldo de um membro (moderação)."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(membro="Quem recebe", valor="Quantidade", motivo="Motivo do ajuste")
    async def grant(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        valor: app_commands.Range[int, 1, 1_000_000],
        motivo: str = "Concedido pela moderação",
    ) -> None:
        assert interaction.guild_id is not None
        new_balance = await self.bot.database.adjust_points(
            interaction.guild_id,
            membro.id,
            valor,
            reason=motivo[:120],
            actor_id=interaction.user.id,
        )
        await interaction.response.send_message(
            (
                f"✅ **{valor:,} pontos** adicionados a **{membro.display_name}**. "
                f"Novo saldo: **{new_balance:,}**."
            ).replace(",", ".")
        )


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(PointsCog(bot))
