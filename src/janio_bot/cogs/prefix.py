# mypy: disable-error-code="arg-type,call-arg"
from __future__ import annotations

import logging
from typing import Literal, TypeVar, cast

import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.cogs.announcements import AnnouncementsCog
from janio_bot.cogs.betting import BettingCog
from janio_bot.cogs.league import LeagueCog
from janio_bot.cogs.music import MusicCog
from janio_bot.cogs.points import PointsCog
from janio_bot.config import RuntimeMode
from janio_bot.ui import make_embed, Colors

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
    embed = make_embed(
        title="📖 Central de Comandos do Janio Bot",
        description=(
            "Olá! Aqui estão todos os comandos que você pode utilizar.\n\n"
            "💡 **Dica de uso:** Você pode usar `j!` no lugar da barra `/`. Se precisar digitar "
            "textos com espaço (como o título de uma aposta), coloque-os entre aspas `\"\"`.\n"
            "Os comandos com `/` originais continuam funcionando normalmente."
        ),
    )
    embed.add_field(
        name="🛠️ Sistema Geral",
        value=(
            "**`j!ajuda`** — Mostra este menu detalhado.\n"
            "**`j!ping`** — Testa a velocidade e conexão do bot.\n"
            "**`j!janio`** — Exibe informações gerais sobre o bot."
        ),
        inline=False,
    )
    embed.add_field(
        name="💰 Economia e Pontos",
        value=(
            "**`j!pontos saldo [@membro]`** — Veja o saldo da sua conta ou de outro membro.\n"
            "**`j!pontos diario`** — Resgate seu bônus diário gratuito (a cada 24h).\n"
            "**`j!pontos ranking`** — Consulte o top 10 dos membros mais ricos."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 Previsões e Apostas",
        value=(
            "**`j!aposta abertas`** — Veja todos os mercados abertos para apostar.\n"
            "**`j!aposta ver <id>`** — Mostra o placar e detalhes de uma aposta.\n"
            "**`j!aposta apostar <id> <A|B> <valor>`** — Aposte no lado vencedor."
        ),
        inline=False,
    )
    embed.add_field(
        name="⚔️ League of Legends",
        value=(
            "**`j!lol build <campeão>`** — Sugere os melhores itens do meta atual.\n"
            "**`j!lol runas <campeão>`** — Traz as runas mais fortes para o campeão.\n"
            "**`j!lol jogador <nome> <tag> [região]`** — Busca o histórico do jogador."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎵 Música e Entretenimento",
        value=(
            "**`j!p <busca>`** ou **`j!musica tocar <busca>`** — Adiciona áudio do YouTube.\n"
            "**`j!musica fila`** — Mostra a lista de faixas que vão tocar a seguir.\n"
            "**`j!musica pausar`** / **`continuar`** — Pausa ou retoma a música.\n"
            "**`j!musica pular`** — Pula direto para a próxima música da fila.\n"
            "**`j!musica parar`** / **`sair`** — Encerra a fila e desconecta o bot."
        ),
        inline=False,
    )
    embed.set_footer(text="🔧 Quer ver os comandos de administrador? Digite: j!ajuda moderacao")
    return embed


def _moderation_help(mode: RuntimeMode) -> discord.Embed:
    lines = [
        "Estes comandos são restritos apenas a membros com permissão de Gerenciar Servidor.\n",
        "**`j!pontos dar @membro <valor> [motivo]`**",
        "↳ Cria pontos e os adiciona diretamente na conta do membro.\n",
        "**`j!aviso configurar #canal [segundos] [mensagem]`**",
        "↳ Configura uma mensagem automática que se repete no canal escolhido.\n",
        "**`j!aviso ativar`** · **`j!aviso desativar`** · **`j!aviso testar`**",
        "↳ Controles de status para ligar/desligar o sistema de avisos.\n",
        "**`j!aposta criar \"título\" \"opção A\" \"opção B\" [minutos]`**",
        "↳ Cria um mercado de apostas. Textos com espaço devem estar entre aspas `\"\"`.\n",
        "**`j!aposta fechar <id>`**",
        "↳ Bloqueia novas apostas (os membros aguardam o resultado).\n",
        "**`j!aposta resolver <id> <A|B>`**",
        "↳ Encerra o evento e distribui todo o pote para quem apostou certo.\n",
        "**`j!aposta cancelar <id>`**",
        "↳ Cancela o evento e devolve 100% dos pontos aos participantes."
    ]
    return make_embed(
        title="🛡️ Painel de Moderação",
        description="\n".join(lines),
        color=Colors.WARNING,
    )


class PrefixCommandsCog(commands.Cog):
    """Message commands that mirror the slash-command hierarchy."""

    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    def _cog(self, cls: type[CogT]) -> CogT:
        for cog in self.bot.cogs.values():
            if isinstance(cog, cls):
                return cog
        raise commands.CommandError(f"O módulo {cls.__name__} não está disponível.")

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

    @app_commands.command(name="ajuda", description="Mostra a central de comandos do bot.")
    async def slash_help(self, interaction: discord.Interaction) -> None:
        embed = _command_help(self.bot.settings.mode)
        await interaction.response.send_message(embed=embed)

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
            "Use `j!pontos saldo`, `j!pontos diario`, `j!pontos ranking` ou "
            "`j!pontos dar`."
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
            "Use `j!aviso configurar`, `j!aviso ativar`, `j!aviso desativar`, "
            "`j!aviso status` ou `j!aviso testar`."
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
            "Use `j!musica tocar`, `j!musica fila`, `j!musica pausar`, "
            "`j!musica continuar`, `j!musica pular`, `j!musica parar` ou `j!musica sair`."
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

    @commands.command(name="p", aliases=("play",))
    @commands.guild_only()
    async def play_shortcut(
        self,
        context: commands.Context[JanioBot],
        *,
        busca: str,
    ) -> None:
        cog = self._cog(MusicCog)
        await MusicCog.play.callback(cog, _as_interaction(context), busca)


class PrefixBettingCog(commands.Cog):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot

    def _betting(self) -> BettingCog:
        for cog in self.bot.cogs.values():
            if isinstance(cog, BettingCog):
                return cog
        raise commands.CommandError("As previsões não estão disponíveis agora.")

    @commands.group(name="aposta", invoke_without_command=True)
    @commands.guild_only()
    async def bet_group(self, context: commands.Context[JanioBot]) -> None:
        await context.send(
            "Use `j!aposta abertas`, `j!aposta ver`, `j!aposta apostar`, "
            "`j!aposta criar`, `j!aposta fechar`, `j!aposta resolver` ou "
            "`j!aposta cancelar`."
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
        for cog in self.bot.cogs.values():
            if isinstance(cog, LeagueCog):
                return cog
        raise commands.CommandError("Os comandos de League of Legends não estão disponíveis agora.")

    @commands.group(name="lol", invoke_without_command=True)
    async def league_group(self, context: commands.Context[JanioBot]) -> None:
        await context.send("Use `j!lol build`, `j!lol runas` ou `j!lol jogador`.")

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
    await bot.add_cog(PrefixBettingCog(bot))
    await bot.add_cog(PrefixLeagueCog(bot))
