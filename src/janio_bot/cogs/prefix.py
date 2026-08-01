# mypy: disable-error-code="arg-type,call-arg"
from __future__ import annotations

import logging
from typing import Literal, TypeVar, cast

import discord
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.cogs.announcements import AnnouncementsCog
from janio_bot.cogs.betting import BettingCog
from janio_bot.cogs.league import LeagueCog
from janio_bot.cogs.music import MusicCog
from janio_bot.cogs.points import PointsCog
from janio_bot.config import RuntimeMode

LOGGER = logging.getLogger(__name__)

CogT = TypeVar("CogT", bound=commands.Cog)


class _PrefixResponse:
    """Small Interaction response bridge used by the prefix wrappers."""

    def __init__(self, interaction: _PrefixInteraction) -> None:
        self.interaction = interaction
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool = False, thinking: bool = False) -> None:
        del ephemeral, thinking
        self._done = True

    async def send_message(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ) -> None:
        del ephemeral
        if embed is None:
            self.interaction.last_message = await self.interaction.context.send(content)
        else:
            self.interaction.last_message = await self.interaction.context.send(
                content,
                embed=embed,
            )
        self._done = True


class _PrefixFollowup:
    def __init__(self, interaction: _PrefixInteraction) -> None:
        self.interaction = interaction

    async def send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ) -> None:
        del ephemeral
        if embed is None:
            self.interaction.last_message = await self.interaction.context.send(content)
        else:
            self.interaction.last_message = await self.interaction.context.send(
                content,
                embed=embed,
            )


class _PrefixInteraction:
    """Context-shaped adapter for sharing the existing slash command callbacks."""

    def __init__(self, context: commands.Context[JanioBot]) -> None:
        self.context = context
        self.response = _PrefixResponse(self)
        self.followup = _PrefixFollowup(self)
        self.last_message: discord.Message | None = None

    @property
    def guild(self) -> discord.Guild | None:
        return self.context.guild

    @property
    def guild_id(self) -> int | None:
        return self.context.guild.id if self.context.guild is not None else None

    @property
    def channel_id(self) -> int | None:
        return self.context.channel.id if self.context.channel is not None else None

    @property
    def user(self) -> discord.Member | discord.User:
        return self.context.author

    async def edit_original_response(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
    ) -> discord.Message:
        if self.last_message is None:
            if embed is None:
                self.last_message = await self.context.send(content)
            else:
                self.last_message = await self.context.send(content, embed=embed)
        else:
            await self.last_message.edit(content=content, embed=embed)
        return self.last_message

    async def original_response(self) -> discord.Message:
        if self.last_message is None:
            raise RuntimeError("O comando ainda não enviou uma resposta.")
        return self.last_message


def _as_interaction(context: commands.Context[JanioBot]) -> discord.Interaction:
    # The callbacks only use the Interaction surface implemented by the adapter above.
    return cast(discord.Interaction, _PrefixInteraction(context))


def _command_help(mode: RuntimeMode) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Comandos do Janio Bot",
        description=(
            "Use `!` no lugar de `/`. Textos com espaço podem ser colocados entre aspas.\n"
            "Os comandos com `/` continuam funcionando normalmente."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Geral e pontos",
        value=(
            "`!janio` · `!ping` · `!ajuda`\n"
            "`!pontos saldo [@membro]` · `!pontos diario` · `!pontos ranking`"
        ),
        inline=False,
    )
    if mode is RuntimeMode.COMMUNITY:
        embed.add_field(
            name="Previsões",
            value=(
                "`!aposta abertas` · `!aposta ver <id>`\n"
                "`!aposta apostar <id> <A|B> <valor>`"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="League of Legends",
            value=(
                "`!lol build <campeão>` · `!lol runas <campeão>`\n"
                "`!lol jogador <nome> <tag> [região]`"
            ),
            inline=False,
        )
    embed.add_field(
        name="Música e aviso",
        value=(
            "`!musica tocar <busca>` · `!musica fila` · `!musica pular`\n"
            "`!aviso status`"
        ),
        inline=False,
    )
    embed.set_footer(text="Use !ajuda moderacao para ver os comandos administrativos.")
    return embed


def _moderation_help(mode: RuntimeMode) -> discord.Embed:
    lines = [
        "`!pontos dar @membro <valor> [motivo]`",
        "`!aviso configurar #canal [segundos] [mensagem]`",
        "`!aviso ativar` · `!aviso desativar` · `!aviso testar`",
    ]
    if mode is RuntimeMode.COMMUNITY:
        lines.extend(
            [
                '`!aposta criar "título" "opção A" "opção B" [minutos]`',
                "`!aposta fechar <id>` · `!aposta resolver <id> <A|B>`",
                "`!aposta cancelar <id>`",
            ]
        )
    return discord.Embed(
        title="🛡️ Comandos de moderação",
        description="\n".join(lines),
        color=discord.Color.orange(),
    )


class PrefixCommandsCog(commands.Cog):
    """Message commands that mirror the slash-command hierarchy."""

    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    def _cog(self, cog_type: type[CogT]) -> CogT:
        cog = self.bot.get_cog(cog_type.__name__)
        if not isinstance(cog, cog_type):
            raise commands.CommandError("Este recurso não está disponível agora.")
        return cog

    @commands.command(name="ajuda", aliases=("help", "comandos"))
    async def help_command(
        self,
        context: commands.Context[JanioBot],
        secao: str | None = None,
    ) -> None:
        moderation = secao is not None and secao.casefold() in {
            "admin",
            "adm",
            "moderacao",
            "moderação",
        }
        embed = (
            _moderation_help(self.bot.settings.mode)
            if moderation
            else _command_help(self.bot.settings.mode)
        )
        await context.send(embed=embed)

    @commands.command(name="janio")
    async def janio(self, context: commands.Context[JanioBot]) -> None:
        await context.send(embed=_command_help(self.bot.settings.mode))

    @commands.command(name="ping")
    async def ping(self, context: commands.Context[JanioBot]) -> None:
        await context.send(f"🏓 Pong! `{round(self.bot.latency * 1000)} ms`")

    @commands.group(name="pontos", invoke_without_command=True)
    @commands.guild_only()
    async def points(self, context: commands.Context[JanioBot]) -> None:
        await context.send(
            "Use `!pontos saldo`, `!pontos diario`, `!pontos ranking` ou "
            "`!pontos dar`."
        )

    @points.command(name="saldo")
    async def balance(
        self,
        context: commands.Context[JanioBot],
        membro: discord.Member | None = None,
    ) -> None:
        cog = self._cog(PointsCog)
        await PointsCog.balance.callback(cog, _as_interaction(context), membro)

    @points.command(name="diario", aliases=("diário",))
    async def daily(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(PointsCog)
        await PointsCog.daily.callback(cog, _as_interaction(context))

    @points.command(name="ranking")
    async def ranking(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(PointsCog)
        await PointsCog.ranking.callback(cog, _as_interaction(context))

    @points.command(name="dar")
    @commands.has_guild_permissions(manage_guild=True)
    async def grant(
        self,
        context: commands.Context[JanioBot],
        membro: discord.Member,
        valor: int,
        *,
        motivo: str = "Concedido pela moderação",
    ) -> None:
        if not 1 <= valor <= 1_000_000:
            raise commands.BadArgument("O valor precisa estar entre 1 e 1.000.000.")
        cog = self._cog(PointsCog)
        await PointsCog.grant.callback(
            cog,
            _as_interaction(context),
            membro,
            valor,
            motivo,
        )

    @commands.group(name="aviso", invoke_without_command=True)
    @commands.guild_only()
    async def announcement(self, context: commands.Context[JanioBot]) -> None:
        await context.send(
            "Use `!aviso configurar`, `!aviso ativar`, `!aviso desativar`, "
            "`!aviso status` ou `!aviso testar`."
        )

    @announcement.command(name="configurar")
    @commands.has_guild_permissions(manage_guild=True)
    async def configure_announcement(
        self,
        context: commands.Context[JanioBot],
        canal: discord.TextChannel,
        intervalo_segundos: int | None = None,
        *,
        mensagem: str | None = None,
    ) -> None:
        if intervalo_segundos is not None and not 30 <= intervalo_segundos <= 86_400:
            raise commands.BadArgument("O intervalo precisa estar entre 30 e 86.400 segundos.")
        cog = self._cog(AnnouncementsCog)
        await AnnouncementsCog.configure.callback(
            cog,
            _as_interaction(context),
            canal,
            intervalo_segundos,
            mensagem,
        )

    @announcement.command(name="ativar")
    @commands.has_guild_permissions(manage_guild=True)
    async def enable_announcement(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(AnnouncementsCog)
        await AnnouncementsCog.enable.callback(cog, _as_interaction(context))

    @announcement.command(name="desativar")
    @commands.has_guild_permissions(manage_guild=True)
    async def disable_announcement(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(AnnouncementsCog)
        await AnnouncementsCog.disable.callback(cog, _as_interaction(context))

    @announcement.command(name="status")
    async def announcement_status(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(AnnouncementsCog)
        await AnnouncementsCog.status.callback(cog, _as_interaction(context))

    @announcement.command(name="testar")
    @commands.has_guild_permissions(manage_guild=True)
    async def test_announcement(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(AnnouncementsCog)
        await AnnouncementsCog.test.callback(cog, _as_interaction(context))

    @commands.group(name="musica", aliases=("música",), invoke_without_command=True)
    @commands.guild_only()
    async def music(self, context: commands.Context[JanioBot]) -> None:
        await context.send(
            "Use `!musica tocar`, `!musica fila`, `!musica pausar`, "
            "`!musica continuar`, `!musica pular`, `!musica parar` ou `!musica sair`."
        )

    @music.command(name="tocar", aliases=("play",))
    async def play(
        self,
        context: commands.Context[JanioBot],
        *,
        busca: str,
    ) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.play.callback(cog, _as_interaction(context), busca)

    @music.command(name="fila", aliases=("queue",))
    async def queue(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.queue.callback(cog, _as_interaction(context))

    @music.command(name="pausar", aliases=("pause",))
    async def pause(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.pause.callback(cog, _as_interaction(context))

    @music.command(name="continuar", aliases=("resume",))
    async def resume(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.resume.callback(cog, _as_interaction(context))

    @music.command(name="pular", aliases=("skip",))
    async def skip(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.skip.callback(cog, _as_interaction(context))

    @music.command(name="parar", aliases=("stop",))
    async def stop(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.stop.callback(cog, _as_interaction(context))

    @music.command(name="sair", aliases=("leave",))
    async def leave(self, context: commands.Context[JanioBot]) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.leave.callback(cog, _as_interaction(context))


class PrefixBettingCog(commands.Cog):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    def _betting(self) -> BettingCog:
        cog = self.bot.get_cog(BettingCog.__name__)
        if not isinstance(cog, BettingCog):
            raise commands.CommandError("As previsões não estão disponíveis agora.")
        return cog

    @commands.group(name="aposta", invoke_without_command=True)
    @commands.guild_only()
    async def bet_group(self, context: commands.Context[JanioBot]) -> None:
        await context.send(
            "Use `!aposta abertas`, `!aposta ver`, `!aposta apostar`, "
            "`!aposta criar`, `!aposta fechar`, `!aposta resolver` ou "
            "`!aposta cancelar`."
        )

    @bet_group.command(name="criar")
    @commands.has_guild_permissions(manage_guild=True)
    async def create(
        self,
        context: commands.Context[JanioBot],
        titulo: str,
        opcao_a: str,
        opcao_b: str,
        duracao_minutos: int | None = None,
    ) -> None:
        if duracao_minutos is not None and not 1 <= duracao_minutos <= 1440:
            raise commands.BadArgument("A duração precisa estar entre 1 e 1.440 minutos.")
        cog = self._betting()
        await BettingCog.create.callback(
            cog,
            _as_interaction(context),
            titulo,
            opcao_a,
            opcao_b,
            duracao_minutos,
        )

    @bet_group.command(name="apostar")
    async def bet(
        self,
        context: commands.Context[JanioBot],
        mercado: int,
        opcao: str,
        valor: int,
    ) -> None:
        normalized_option = opcao.upper()
        if normalized_option not in {"A", "B"}:
            raise commands.BadArgument("A opção precisa ser A ou B.")
        if not 1 <= valor <= 1_000_000:
            raise commands.BadArgument("O valor precisa estar entre 1 e 1.000.000.")
        cog = self._betting()
        await BettingCog.bet.callback(
            cog,
            _as_interaction(context),
            mercado,
            cast(Literal["A", "B"], normalized_option),
            valor,
        )

    @bet_group.command(name="ver")
    async def show(self, context: commands.Context[JanioBot], mercado: int) -> None:
        cog = self._betting()
        await BettingCog.show.callback(cog, _as_interaction(context), mercado)

    @bet_group.command(name="abertas")
    async def open_markets(self, context: commands.Context[JanioBot]) -> None:
        cog = self._betting()
        await BettingCog.open_markets.callback(cog, _as_interaction(context))

    @bet_group.command(name="fechar")
    @commands.has_guild_permissions(manage_guild=True)
    async def close(self, context: commands.Context[JanioBot], mercado: int) -> None:
        cog = self._betting()
        await BettingCog.close.callback(cog, _as_interaction(context), mercado)

    @bet_group.command(name="resolver")
    @commands.has_guild_permissions(manage_guild=True)
    async def settle(
        self,
        context: commands.Context[JanioBot],
        mercado: int,
        vencedora: str,
    ) -> None:
        normalized_option = vencedora.upper()
        if normalized_option not in {"A", "B"}:
            raise commands.BadArgument("A opção vencedora precisa ser A ou B.")
        cog = self._betting()
        await BettingCog.settle.callback(
            cog,
            _as_interaction(context),
            mercado,
            cast(Literal["A", "B"], normalized_option),
        )

    @bet_group.command(name="cancelar")
    @commands.has_guild_permissions(manage_guild=True)
    async def cancel(self, context: commands.Context[JanioBot], mercado: int) -> None:
        cog = self._betting()
        await BettingCog.cancel.callback(cog, _as_interaction(context), mercado)


class PrefixLeagueCog(commands.Cog):
    REGIONS = {"br1", "na1", "la1", "la2", "euw1", "eun1", "kr", "jp1"}

    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    def _league(self) -> LeagueCog:
        cog = self.bot.get_cog(LeagueCog.__name__)
        if not isinstance(cog, LeagueCog):
            raise commands.CommandError("Os comandos de LoL não estão disponíveis agora.")
        return cog

    @commands.group(name="lol", invoke_without_command=True)
    async def league_group(self, context: commands.Context[JanioBot]) -> None:
        await context.send("Use `!lol build`, `!lol runas` ou `!lol jogador`.")

    @league_group.command(name="build")
    async def build(
        self,
        context: commands.Context[JanioBot],
        *,
        campeao: str,
    ) -> None:
        cog = self._league()
        await LeagueCog.build.callback(cog, _as_interaction(context), campeao)

    @league_group.command(name="runas")
    async def runes(
        self,
        context: commands.Context[JanioBot],
        *,
        campeao: str,
    ) -> None:
        cog = self._league()
        await LeagueCog.runes.callback(cog, _as_interaction(context), campeao)

    @league_group.command(name="jogador")
    async def player(
        self,
        context: commands.Context[JanioBot],
        nome: str,
        tag: str,
        regiao: str = "br1",
    ) -> None:
        normalized_region = regiao.casefold()
        if normalized_region not in self.REGIONS:
            raise commands.BadArgument("Região inválida. Exemplo para o Brasil: br1.")
        cog = self._league()
        await LeagueCog.player.callback(
            cog,
            _as_interaction(context),
            nome,
            tag,
            cast(
                Literal["br1", "na1", "la1", "la2", "euw1", "eun1", "kr", "jp1"],
                normalized_region,
            ),
        )


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(PrefixCommandsCog(bot))
    if bot.settings.mode is RuntimeMode.COMMUNITY:
        await bot.add_cog(PrefixBettingCog(bot))
    else:
        await bot.add_cog(PrefixLeagueCog(bot))
