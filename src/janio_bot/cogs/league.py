from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.services.ddragon import Champion, normalize_champion_name
from janio_bot.services.metabot import BuildRecommendation

TIER_NAMES = {
    "IRON": "Ferro",
    "BRONZE": "Bronze",
    "SILVER": "Prata",
    "GOLD": "Ouro",
    "PLATINUM": "Platina",
    "EMERALD": "Esmeralda",
    "DIAMOND": "Diamante",
    "MASTER": "Mestre",
    "GRANDMASTER": "Grão-Mestre",
    "CHALLENGER": "Desafiante",
}


def build_embed(
    champion: Champion,
    recommendation: BuildRecommendation,
    *,
    runes_only: bool = False,
) -> discord.Embed:
    title = (
        f"Runas observadas — {champion.name}"
        if runes_only
        else f"Build observada — {champion.name}"
    )
    embed = discord.Embed(
        title=title,
        url=recommendation.page_url,
        description=(
            f"Dados agregados de partidas no patch **{recommendation.patch}**.\n"
            f"[Ver análise completa no MetaBot.GG]({recommendation.page_url})"
        ),
        color=discord.Color.from_rgb(0, 240, 255),
    )
    embed.set_thumbnail(url=recommendation.image_url or champion.image_url)
    if not runes_only:
        embed.add_field(
            name="🛒 Itens principais",
            value=(
                " → ".join(recommendation.items)
                if recommendation.items
                else "Sem dados de itens."
            )[:1024],
            inline=False,
        )
    embed.add_field(
        name="✨ Runas",
        value=(
            "\n".join(f"• {rune}" for rune in recommendation.runes)
            if recommendation.runes
            else "Sem dados de runas."
        )[:1024],
        inline=False,
    )
    embed.set_footer(
        text=(
            f"Fonte: MetaBot.GG • Catálogo/imagens: Riot Data Dragon "
            f"{champion.version} • Não é recomendação oficial da Riot"
        )
    )
    return embed


class LeagueCog(
    commands.GroupCog,
    group_name="lol",
    group_description="Builds, runas e perfis de League of Legends.",
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    async def _recommendation(
        self, interaction: discord.Interaction, champion_query: str
    ) -> tuple[Champion, BuildRecommendation]:
        await interaction.response.defer(thinking=True)
        champion = await self.bot.ddragon.resolve_champion(champion_query)
        recommendation = await self.bot.metabot.get_build(champion.name)
        return champion, recommendation

    @app_commands.command(
        name="build", description="Mostra itens e runas observados no patch atual."
    )
    @app_commands.describe(campeao="Nome do campeão, por exemplo Jinx")
    async def build(self, interaction: discord.Interaction, campeao: str) -> None:
        champion, recommendation = await self._recommendation(interaction, campeao)
        await interaction.edit_original_response(
            embed=build_embed(champion, recommendation)
        )

    @app_commands.command(
        name="runas", description="Mostra as runas observadas para um campeão."
    )
    @app_commands.describe(campeao="Nome do campeão, por exemplo Aatrox")
    async def runes(self, interaction: discord.Interaction, campeao: str) -> None:
        champion, recommendation = await self._recommendation(interaction, campeao)
        await interaction.edit_original_response(
            embed=build_embed(champion, recommendation, runes_only=True)
        )

    async def champion_autocomplete(
        self, _interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        champions = await self.bot.ddragon.champions()
        normalized = normalize_champion_name(current)
        starts = [
            champion
            for champion in champions
            if normalize_champion_name(champion.name).startswith(normalized)
            or normalize_champion_name(champion.id).startswith(normalized)
        ]
        contains = [
            champion
            for champion in champions
            if champion not in starts
            and (
                normalized in normalize_champion_name(champion.name)
                or normalized in normalize_champion_name(champion.id)
            )
        ]
        selected = (starts + contains)[:25]
        return [
            app_commands.Choice(name=champion.name, value=champion.name)
            for champion in selected
        ]

    @build.autocomplete("campeao")
    async def build_champion_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.champion_autocomplete(interaction, current)

    @runes.autocomplete("campeao")
    async def runes_champion_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.champion_autocomplete(interaction, current)

    @app_commands.command(
        name="jogador", description="Consulta nível e ranks de um Riot ID."
    )
    @app_commands.checks.cooldown(2, 15.0)
    @app_commands.describe(
        nome="Nome antes do #",
        tag="Tag depois do #",
        regiao="Servidor da conta",
    )
    async def player(
        self,
        interaction: discord.Interaction,
        nome: str,
        tag: str,
        regiao: Literal["br1", "na1", "la1", "la2", "euw1", "eun1", "kr", "jp1"] = "br1",
    ) -> None:
        await interaction.response.defer(thinking=True)
        profile = await self.bot.riot.get_profile(nome, tag, platform=regiao)
        embed = discord.Embed(
            title=f"{profile.game_name}#{profile.tag_line}",
            description=f"Nível **{profile.summoner_level}** • Região **{regiao.upper()}**",
            color=discord.Color.gold(),
        )
        champions = await self.bot.ddragon.champions()
        if champions and profile.profile_icon_id:
            version = champions[0].version
            embed.set_thumbnail(
                url=(
                    f"{self.bot.settings.ddragon_base_url}/cdn/{version}/img/"
                    f"profileicon/{profile.profile_icon_id}.png"
                )
            )
        if profile.ranks:
            for rank in profile.ranks:
                games = rank.wins + rank.losses
                win_rate = round(rank.wins / games * 100) if games else 0
                embed.add_field(
                    name=rank.queue_name,
                    value=(
                        f"**{TIER_NAMES.get(rank.tier, rank.tier.title())} "
                        f"{rank.rank}** — {rank.league_points} PdL\n"
                        f"{rank.wins}V / {rank.losses}D • {win_rate}% WR"
                    ),
                    inline=True,
                )
        else:
            embed.add_field(
                name="Ranqueadas",
                value="Sem classificação Solo/Duo ou Flex.",
                inline=False,
            )
        embed.set_footer(text="Dados oficiais: Riot Games API")
        await interaction.edit_original_response(embed=embed)


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(LeagueCog(bot))
