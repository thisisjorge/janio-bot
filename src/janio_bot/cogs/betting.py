from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from janio_bot.bot import JanioBot
from janio_bot.models import MarketSnapshot, MarketStatus

LOGGER = logging.getLogger(__name__)

STATUS_LABELS = {
    MarketStatus.OPEN: "🟢 Aberta",
    MarketStatus.CLOSED: "🟡 Fechada",
    MarketStatus.SETTLED: "✅ Resolvida",
    MarketStatus.CANCELLED: "⚪ Cancelada",
}

STATUS_DETAILS = {
    MarketStatus.OPEN: "Use `/aposta apostar` com o número deste mercado.",
    MarketStatus.CLOSED: "As apostas estão encerradas; aguarde o resultado.",
    MarketStatus.SETTLED: "O resultado desta previsão já foi registrado.",
    MarketStatus.CANCELLED: "Esta previsão foi cancelada e as apostas foram devolvidas.",
}

EMBED_DESCRIPTION_LIMIT = 4096


def market_embed(snapshot: MarketSnapshot) -> discord.Embed:
    market = snapshot.market
    color = {
        MarketStatus.OPEN: discord.Color.green(),
        MarketStatus.CLOSED: discord.Color.orange(),
        MarketStatus.SETTLED: discord.Color.blurple(),
        MarketStatus.CANCELLED: discord.Color.light_grey(),
    }[market.status]
    embed = discord.Embed(
        title=f"🎯 Previsão #{market.id}: {market.title}",
        description=(
            f"**Status:** {STATUS_LABELS[market.status]}\n"
            f"{STATUS_DETAILS[market.status]}"
        ),
        color=color,
    )
    winner_a = " 🏆" if market.winning_option == "A" else ""
    winner_b = " 🏆" if market.winning_option == "B" else ""
    embed.add_field(
        name=f"🅰️ {market.option_a}{winner_a}",
        value=(
            f"**{snapshot.option_a_points:,}** pontos\n"
            f"{snapshot.option_a_users} participante(s)"
        ).replace(",", "."),
        inline=True,
    )
    embed.add_field(
        name=f"🅱️ {market.option_b}{winner_b}",
        value=(
            f"**{snapshot.option_b_points:,}** pontos\n"
            f"{snapshot.option_b_users} participante(s)"
        ).replace(",", "."),
        inline=True,
    )
    embed.add_field(
        name="Pote",
        value=f"**{snapshot.total_points:,} pontos**".replace(",", "."),
        inline=False,
    )
    if market.closes_at is not None:
        embed.add_field(
            name="Fechamento",
            value=f"<t:{market.closes_at}:F> • <t:{market.closes_at}:R>",
            inline=False,
        )
    embed.set_footer(
        text="Só pontos virtuais — sem compra, saque, transferência ou prêmio real."
    )
    return embed


def open_markets_description(markets: Sequence[MarketSnapshot]) -> str:
    lines = [
        (
            f"**#{snapshot.market.id} — {snapshot.market.title[:150]}**\n"
            f"🅰️ {snapshot.market.option_a[:80]} ({snapshot.option_a_points:,}) • "
            f"🅱️ {snapshot.market.option_b[:80]} ({snapshot.option_b_points:,})"
        ).replace(",", ".")
        for snapshot in markets
    ]
    selected: list[str] = []
    for line in lines:
        candidate_lines = [*selected, line]
        omitted = len(lines) - len(candidate_lines)
        suffix = (
            f"… e mais {omitted} previsão(ões). Use `/aposta ver` para consultar uma delas."
            if omitted
            else ""
        )
        candidate = "\n\n".join([*candidate_lines, *([suffix] if suffix else [])])
        if len(candidate) > EMBED_DESCRIPTION_LIMIT:
            break
        selected.append(line)

    omitted = len(lines) - len(selected)
    if omitted:
        selected.append(
            f"… e mais {omitted} previsão(ões). Use `/aposta ver` para consultar uma delas."
        )
    return "\n\n".join(selected)


class BettingCog(
    commands.GroupCog,
    group_name="aposta",
    group_description="Previsões com pontos virtuais.",
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.expire_markets.start()

    async def cog_unload(self) -> None:
        self.expire_markets.cancel()

    @app_commands.command(name="criar", description="Cria uma previsão com duas opções.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        titulo="Pergunta da previsão",
        opcao_a="Primeira opção",
        opcao_b="Segunda opção",
        duracao_minutos="Tempo para apostar; vazio = fechamento manual",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        titulo: str,
        opcao_a: str,
        opcao_b: str,
        duracao_minutos: app_commands.Range[int, 1, 1440] | None = None,
    ) -> None:
        assert interaction.guild_id is not None
        if interaction.channel_id is None:
            await interaction.response.send_message(
                "Este comando precisa ser usado em um canal.", ephemeral=True
            )
            return
        if len(titulo) > 150 or len(opcao_a) > 80 or len(opcao_b) > 80:
            await interaction.response.send_message(
                "Título: até 150 caracteres. Cada opção: até 80.", ephemeral=True
            )
            return
        market = await self.bot.database.create_market(
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
            titulo,
            opcao_a,
            opcao_b,
            duration_minutes=duracao_minutos,
        )
        snapshot = await self.bot.database.get_market_snapshot(
            interaction.guild_id, market.id
        )
        await interaction.response.send_message(embed=market_embed(snapshot))
        message = await interaction.original_response()
        await self.bot.database.attach_market_message(
            interaction.guild_id, market.id, message.id
        )

    @app_commands.command(name="apostar", description="Aposta pontos em uma previsão aberta.")
    @app_commands.guild_only()
    @app_commands.describe(
        mercado="Número mostrado no título da previsão",
        opcao="Escolha A ou B",
        valor="Quantidade de pontos",
    )
    async def bet(
        self,
        interaction: discord.Interaction,
        mercado: int,
        opcao: Literal["A", "B"],
        valor: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        assert interaction.guild_id is not None
        receipt = await self.bot.database.place_bet(
            interaction.guild_id,
            interaction.user.id,
            mercado,
            opcao,
            valor,
        )
        await interaction.response.send_message(
            (
                f"✅ Aposta de **{receipt.amount:,} pontos** na opção "
                f"**{receipt.option}** registrada. Saldo: "
                f"**{receipt.new_balance:,}**."
            ).replace(",", "."),
            ephemeral=True,
        )
        await self.refresh_market_message(interaction.guild_id, mercado)

    @app_commands.command(name="ver", description="Mostra uma previsão pelo número.")
    @app_commands.guild_only()
    async def show(self, interaction: discord.Interaction, mercado: int) -> None:
        assert interaction.guild_id is not None
        snapshot = await self.bot.database.get_market_snapshot(
            interaction.guild_id, mercado
        )
        await interaction.response.send_message(embed=market_embed(snapshot))

    @app_commands.command(name="abertas", description="Lista as previsões abertas.")
    @app_commands.guild_only()
    async def open_markets(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        markets = await self.bot.database.list_open_markets(interaction.guild_id)
        if not markets:
            await interaction.response.send_message(
                "Não há previsões abertas.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="🎯 Previsões abertas",
            description=open_markets_description(markets),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="fechar", description="Impede novas apostas.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def close(self, interaction: discord.Interaction, mercado: int) -> None:
        assert interaction.guild_id is not None
        await self.bot.database.close_market(interaction.guild_id, mercado)
        await interaction.response.send_message(
            f"🔒 Previsão **#{mercado}** fechada para novas apostas."
        )
        await self.refresh_market_message(interaction.guild_id, mercado)

    @app_commands.command(
        name="resolver", description="Define a opção vencedora e distribui o pote."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def settle(
        self,
        interaction: discord.Interaction,
        mercado: int,
        vencedora: Literal["A", "B"],
    ) -> None:
        assert interaction.guild_id is not None
        settlement = await self.bot.database.settle_market(
            interaction.guild_id, mercado, vencedora
        )
        if settlement.refunded_because_no_winners:
            detail = "Ninguém escolheu a vencedora; todas as apostas foram devolvidas."
        else:
            detail = (
                f"Pote de **{settlement.total_pool:,} pontos** distribuído para "
                f"**{len(settlement.payouts)}** vencedor(es)."
            ).replace(",", ".")
        await interaction.response.send_message(
            f"🏆 Previsão **#{mercado}** resolvida: opção **{vencedora}**.\n{detail}"
        )
        await self.refresh_market_message(interaction.guild_id, mercado)

    @app_commands.command(
        name="cancelar", description="Cancela a previsão e devolve todas as apostas."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def cancel(self, interaction: discord.Interaction, mercado: int) -> None:
        assert interaction.guild_id is not None
        result = await self.bot.database.cancel_market(interaction.guild_id, mercado)
        await interaction.response.send_message(
            (
                f"↩️ Previsão **#{mercado}** cancelada. "
                f"**{result.total_refunded:,} pontos** devolvidos a "
                f"**{result.users_refunded}** participante(s)."
            ).replace(",", ".")
        )
        await self.refresh_market_message(interaction.guild_id, mercado)

    async def refresh_market_message(self, guild_id: int, market_id: int) -> None:
        try:
            snapshot = await self.bot.database.get_market_snapshot(guild_id, market_id)
            market = snapshot.market
            if market.message_id is None:
                return
            channel = self.bot.get_channel(market.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(market.channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                return
            message = await channel.fetch_message(market.message_id)
            await message.edit(embed=market_embed(snapshot))
        except (discord.HTTPException, discord.Forbidden, discord.NotFound):
            LOGGER.warning(
                "Não foi possível atualizar o embed do mercado %d/%d.",
                guild_id,
                market_id,
            )

    @tasks.loop(seconds=15)
    async def expire_markets(self) -> None:
        expired = await self.bot.database.close_expired_markets()
        for guild_id, market_id in expired:
            await self.refresh_market_message(guild_id, market_id)

    @expire_markets.before_loop
    async def before_expire_markets(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(BettingCog(bot))
