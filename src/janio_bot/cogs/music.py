from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from functools import partial

import discord
from discord import app_commands
from discord.ext import commands

from janio_bot.bot import JanioBot
from janio_bot.errors import ExternalServiceError
from janio_bot.services.music import Track
from janio_bot.ui import make_embed, make_error_embed, make_success_embed, Colors

LOGGER = logging.getLogger(__name__)

MAX_QUEUED_TRACKS = 25
REQUEST_COOLDOWN_SECONDS = 5.0


@dataclass(slots=True)
class GuildMusicState:
    queue: deque[Track] = field(default_factory=deque)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connection_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    queue_reservations: set[int] = field(default_factory=set)
    last_request_at: dict[int, float] = field(default_factory=dict)
    next_reservation_id: int = 0
    generation: int = 0
    starting: bool = False
    current: Track | None = None
    text_channel_id: int | None = None
    idle_task: asyncio.Task[None] | None = None


def _duration(seconds: int | None) -> str:
    if seconds is None:
        return "duração desconhecida"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:d}:{seconds:02d}"


class MusicCog(
    commands.GroupCog,
    group_name="musica",
    group_description="Reprodução de música no canal de voz.",
):
    def __init__(self, bot: JanioBot) -> None:
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    async def cog_unload(self) -> None:
        for state in self.states.values():
            if state.idle_task is not None:
                state.idle_task.cancel()
        for voice in list(self.bot.voice_clients):
            await voice.disconnect(force=True)

    def _state(self, guild_id: int) -> GuildMusicState:
        return self.states.setdefault(guild_id, GuildMusicState())

    async def _reserve_queue_slot(
        self,
        state: GuildMusicState,
        user_id: int,
        *,
        now: float | None = None,
    ) -> int:
        timestamp = time.monotonic() if now is None else now
        async with state.lock:
            if len(state.queue) + len(state.queue_reservations) >= MAX_QUEUED_TRACKS:
                raise ExternalServiceError(
                    f"A fila atingiu o limite de {MAX_QUEUED_TRACKS} faixas."
                )

            cutoff = timestamp - REQUEST_COOLDOWN_SECONDS
            state.last_request_at = {
                member_id: requested_at
                for member_id, requested_at in state.last_request_at.items()
                if requested_at > cutoff
            }
            previous_request = state.last_request_at.get(user_id)
            if previous_request is not None:
                retry_after = math.ceil(
                    REQUEST_COOLDOWN_SECONDS - (timestamp - previous_request)
                )
                raise ExternalServiceError(
                    f"Aguarde {max(1, retry_after)} segundo(s) antes de pedir outra faixa."
                )

            state.last_request_at[user_id] = timestamp
            state.next_reservation_id += 1
            reservation_id = state.next_reservation_id
            state.queue_reservations.add(reservation_id)
            return reservation_id

    @staticmethod
    async def _release_queue_slot(
        state: GuildMusicState, reservation_id: int
    ) -> None:
        async with state.lock:
            state.queue_reservations.discard(reservation_id)

    @staticmethod
    def _member_voice_channel(
        interaction: discord.Interaction,
    ) -> discord.VoiceChannel | discord.StageChannel:
        if not isinstance(interaction.user, discord.Member):
            raise ExternalServiceError("Use este comando dentro de um servidor.")
        voice_state = interaction.user.voice
        if voice_state is None or voice_state.channel is None:
            raise ExternalServiceError("Entre em um canal de voz primeiro.")
        return voice_state.channel

    async def _connected_voice(
        self, interaction: discord.Interaction
    ) -> discord.VoiceClient:
        channel = self._member_voice_channel(interaction)
        guild = interaction.guild
        assert guild is not None
        voice = guild.voice_client
        if isinstance(voice, discord.VoiceClient) and not voice.is_connected():
            await voice.disconnect(force=True)
            voice = None
        if voice is None:
            connected: discord.VoiceProtocol = await channel.connect()
            if not isinstance(connected, discord.VoiceClient):
                raise ExternalServiceError("Não consegui abrir a conexão de voz.")
            return connected
        if not isinstance(voice, discord.VoiceClient):
            raise ExternalServiceError("A conexão de voz está em um estado inválido.")
        if voice.channel.id != channel.id:
            raise ExternalServiceError(
                "O bot já está tocando em outro canal de voz deste servidor."
            )
        return voice

    @app_commands.command(name="tocar", description="Busca ou enfileira uma música.")
    @app_commands.guild_only()
    @app_commands.describe(busca="Nome da música ou link do YouTube")
    async def play(self, interaction: discord.Interaction, busca: str) -> None:
        assert interaction.guild_id is not None
        self._member_voice_channel(interaction)
        state = self._state(interaction.guild_id)
        reservation_id = await self._reserve_queue_slot(state, interaction.user.id)
        committed = False
        try:
            await interaction.response.defer(thinking=True)
            track = await self.bot.music_extractor.extract(busca, interaction.user.id)
            async with state.connection_lock:
                async with state.lock:
                    if reservation_id not in state.queue_reservations:
                        raise ExternalServiceError(
                            "A reserva desta faixa não está mais ativa."
                        )
                voice = await self._connected_voice(interaction)
                async with state.lock:
                    if reservation_id not in state.queue_reservations:
                        raise ExternalServiceError(
                            "A reserva desta faixa não está mais ativa."
                        )
                    state.queue_reservations.remove(reservation_id)
                    state.queue.append(track)
                    state.text_channel_id = interaction.channel_id
                    if state.idle_task is not None:
                        state.idle_task.cancel()
                        state.idle_task = None
                    position = len(state.queue)
                    committed = True
        finally:
            if not committed:
                await self._release_queue_slot(state, reservation_id)
        await self._start_next(interaction.guild_id, voice)
        embed = make_embed(
            title="🎵 Música adicionada à fila",
            description=f"**{discord.utils.escape_markdown(track.title)}**\n⏱️ Duração: `{_duration(track.duration_seconds)}`\n🔢 Posição: `{position}`",
            color=Colors.SUCCESS
        )
        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="fila", description="Mostra a fila de reprodução.")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        state = self._state(interaction.guild_id)
        lines = []
        if state.current is not None:
            lines.append(
                f"▶️ **Agora:** {discord.utils.escape_markdown(state.current.title)}"
            )
        for index, track in enumerate(list(state.queue)[:10], start=1):
            lines.append(
                f"`{index}.` {discord.utils.escape_markdown(track.title)} "
                f"(`{_duration(track.duration_seconds)}`)"
            )
        if not lines:
            await interaction.response.send_message(embed=make_error_embed("A fila está vazia."), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=make_embed(
                title="🎶 Fila de música",
                description="\n".join(lines)
            )
        )

    @app_commands.command(name="pausar", description="Pausa a faixa atual.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        voice = await self._require_same_voice(interaction)
        if not voice.is_playing():
            raise ExternalServiceError("Não há uma faixa tocando.")
        voice.pause()
        await interaction.response.send_message(embed=make_success_embed("Música pausada."))

    @app_commands.command(name="continuar", description="Continua a faixa pausada.")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        voice = await self._require_same_voice(interaction)
        if not voice.is_paused():
            raise ExternalServiceError("A música não está pausada.")
        voice.resume()
        await interaction.response.send_message(embed=make_success_embed("Reprodução retomada."))

    @app_commands.command(name="pular", description="Pula a faixa atual.")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        voice = await self._require_same_voice(interaction)
        if not voice.is_playing() and not voice.is_paused():
            raise ExternalServiceError("Não há uma faixa para pular.")
        voice.stop()
        await interaction.response.send_message(embed=make_success_embed("Faixa pulada."))

    @app_commands.command(name="parar", description="Limpa a fila e para a reprodução.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        state = self._state(interaction.guild_id)
        async with state.connection_lock:
            voice = await self._require_same_voice(interaction)
            await self._clear_state(state)
            voice.stop()
        await interaction.response.send_message(embed=make_success_embed("Reprodução e fila encerradas."))

    @app_commands.command(name="sair", description="Desconecta o bot do canal de voz.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        state = self._state(interaction.guild_id)
        async with state.connection_lock:
            voice = await self._require_same_voice(interaction)
            await self._clear_state(state)
            await voice.disconnect(force=True)
        await interaction.response.send_message(embed=make_success_embed("Saí do canal de voz."))

    @staticmethod
    async def _clear_state(state: GuildMusicState) -> None:
        async with state.lock:
            state.generation += 1
            state.queue.clear()
            state.queue_reservations.clear()
            state.current = None

    async def _require_same_voice(
        self, interaction: discord.Interaction
    ) -> discord.VoiceClient:
        channel = self._member_voice_channel(interaction)
        guild = interaction.guild
        assert guild is not None
        voice = guild.voice_client
        if not isinstance(voice, discord.VoiceClient) or not voice.is_connected():
            raise ExternalServiceError("O bot não está conectado a um canal de voz.")
        if voice.channel.id != channel.id:
            raise ExternalServiceError("Entre no mesmo canal de voz do bot.")
        return voice

    async def _start_next(self, guild_id: int, voice: discord.VoiceClient) -> None:
        state = self._state(guild_id)
        while True:
            async with state.lock:
                if (
                    voice.is_playing()
                    or voice.is_paused()
                    or state.current is not None
                    or state.starting
                ):
                    return
                if state.idle_task is not None:
                    state.idle_task.cancel()
                    state.idle_task = None
                if not state.queue:
                    state.idle_task = asyncio.create_task(
                        self._disconnect_when_idle(guild_id)
                    )
                    return
                track = state.queue.popleft()
                generation = state.generation
                state.starting = True

            source: discord.AudioSource | None = None
            stale = False
            try:
                track = await self.bot.music_extractor.refresh(track)
                before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                if track.http_headers:
                    headers_list = [f"{k}: {v}" for k, v in track.http_headers.items()]
                    headers_str = "\\r\\n".join(headers_list) + "\\r\\n"
                    before_options += f" -headers \"{headers_str}\""

                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(
                        track.stream_url,
                        executable=self.bot.settings.ffmpeg_path,
                        before_options=before_options,
                        options="-vn",
                    ),
                    volume=0.5,
                )
                async with state.connection_lock, state.lock:
                    if state.generation != generation:
                        state.starting = False
                        stale = True
                    else:
                        state.current = track
                        try:
                            voice.play(
                                source,
                                after=partial(self._after_track, guild_id, track),
                            )
                        except Exception:
                            state.current = None
                            raise
                        finally:
                            state.starting = False
            except asyncio.CancelledError:
                async with state.lock:
                    state.starting = False
                if source is not None:
                    source.cleanup()
                raise
            except Exception:
                async with state.lock:
                    state.starting = False
                    if state.current is track:
                        state.current = None
                if source is not None:
                    source.cleanup()
                LOGGER.exception("Falha ao iniciar uma faixa no servidor %d.", guild_id)
                await self._notify(
                    state,
                    embed=make_error_embed("Não consegui tocar uma faixa da fila; passei para a próxima.")
                )
                continue

            if stale:
                if source is not None:
                    source.cleanup()
                continue
            embed = make_embed(
                title="▶️ Tocando agora",
                description=f"**{discord.utils.escape_markdown(track.title)}**\n⏱️ Duração: `{_duration(track.duration_seconds)}`"
            )
            if track.thumbnail_url:
                embed.set_thumbnail(url=track.thumbnail_url)
            await self._notify(state, embed=embed)
            return

    def _after_track(
        self, guild_id: int, track: Track, error: Exception | None
    ) -> None:
        self.bot.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._finish_track(guild_id, track, error))
        )

    async def _finish_track(
        self, guild_id: int, track: Track, error: Exception | None
    ) -> None:
        if error is not None:
            LOGGER.warning("Erro do player no servidor %d: %s", guild_id, error)
        state = self._state(guild_id)
        async with state.lock:
            if state.current is not track:
                return
            state.current = None
        guild = self.bot.get_guild(guild_id)
        if guild is None or not isinstance(guild.voice_client, discord.VoiceClient):
            return
        await self._start_next(guild_id, guild.voice_client)

    async def _disconnect_when_idle(self, guild_id: int) -> None:
        try:
            await asyncio.sleep(300)
            state = self._state(guild_id)
            async with state.connection_lock:
                guild = self.bot.get_guild(guild_id)
                if guild is None or not isinstance(
                    guild.voice_client, discord.VoiceClient
                ):
                    return
                async with state.lock:
                    if state.queue or state.current is not None or state.starting:
                        return
                await guild.voice_client.disconnect(force=True)
            await self._notify(state, embed=make_embed(title="👋 Ocioso", description="Saí do canal de voz após 5 minutos sem música."))
        except asyncio.CancelledError:
            return

    async def _notify(self, state: GuildMusicState, message: str | None = None, embed: discord.Embed | None = None) -> None:
        if state.text_channel_id is None:
            return
        channel = self.bot.get_channel(state.text_channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                await channel.send(content=message, embed=embed)
            except discord.HTTPException:
                LOGGER.warning("Falha ao enviar atualização da fila de música.")


async def setup(bot: JanioBot) -> None:
    await bot.add_cog(MusicCog(bot))
