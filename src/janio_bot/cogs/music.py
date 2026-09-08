from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from janio_bot.bot import JanioBot
from janio_bot.errors import ExternalServiceError
from janio_bot.services.lastfm import lastfm_service
from janio_bot.ui import make_embed, make_error_embed, make_success_embed, Colors

LOGGER = logging.getLogger(__name__)

def _duration(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
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

    async def cog_unload(self) -> None:
        for vc in self.bot.voice_clients:
            if isinstance(vc, wavelink.Player):
                await vc.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            return

        track = payload.track
        session_keys = await self._get_voice_session_keys(player.guild)
        
        await lastfm_service.update_now_playing(
            track.title, 
            session_keys, 
            track.author if track.author else None
        )

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            return

        track = payload.track
        if track:
            duration = (track.length // 1000) if track.length else 180
            start_ts = int(time.time()) - duration
            session_keys = await self._get_voice_session_keys(player.guild)
            
            await lastfm_service.scrobble(
                track.title, 
                start_ts, 
                session_keys, 
                track.author if track.author else None
            )

    async def _get_voice_session_keys(self, guild: discord.Guild) -> list[str]:
        if not guild.voice_client or not guild.voice_client.channel: # type: ignore
            return []
        
        session_keys = []
        for member in guild.voice_client.channel.members: # type: ignore
            if not member.bot:
                session_key = await self.bot.database.get_lastfm_session(member.id)
                if session_key:
                    session_keys.append(session_key)
        return session_keys

    async def _get_player(self, interaction: discord.Interaction) -> wavelink.Player:
        if not interaction.guild:
            raise ExternalServiceError("Comando apenas para servidores.")
        
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            raise ExternalServiceError("Entre em um canal de voz primeiro.")
            
        voice_channel = interaction.user.voice.channel
        
        if not interaction.guild.voice_client:
            player: wavelink.Player = await voice_channel.connect(cls=wavelink.Player)  # type: ignore
        else:
            player = interaction.guild.voice_client  # type: ignore
            if player.channel.id != voice_channel.id: # type: ignore
                raise ExternalServiceError("O bot já está em outro canal de voz.")
                
        return player

    @app_commands.command(name="tocar", description="Busca ou enfileira uma música.")
    @app_commands.guild_only()
    @app_commands.describe(busca="Nome da música ou link do YouTube")
    async def play(self, interaction: discord.Interaction, busca: str) -> None:
        await interaction.response.defer(thinking=True)
        
        try:
            player = await self._get_player(interaction)
        except ExternalServiceError as e:
            await interaction.followup.send(embed=make_error_embed(str(e)))
            return

        import re
        import httpx
        from janio_bot.services.drive_service import drive_vault_service

        tracks: wavelink.Search = []
        is_youtube = "youtube.com" in busca or "youtu.be" in busca
        
        if not is_youtube:
            try:
                tracks = await wavelink.Playable.search(busca)
            except Exception as e:
                LOGGER.warning(f"Normal search failed: {e}")

        # Se falhou (ou se é youtube puro que o Lavalink não toca mais), tenta os fallbacks
        if not tracks and is_youtube:
            # Extrai video id
            match = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", busca)
            if match:
                video_id = match.group(1)
                
                # 1. Fetch metadata via oEmbed
                title = "Unknown Title"
                thumbnail = None
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json", timeout=5.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            title = data.get("title", title)
                            thumbnail = data.get("thumbnail_url")
                except Exception as e:
                    LOGGER.error(f"oEmbed fetch failed: {e}")

                # 2. Tenta encontrar no cofre do Google Drive primeiro
                local_path = await drive_vault_service.search_by_video_id(video_id)
                if local_path:
                    # Pesquisa como se fosse um arquivo local
                    try:
                        tracks = await wavelink.Playable.search("file://" + local_path)
                        if tracks:
                            # Injeta os metadados reais para a Embed ficar bonita
                            tracks[0].title = title
                            if thumbnail:
                                tracks[0].artwork = thumbnail
                            tracks[0].source = "drive_fallback"
                            tracks[0].uri = busca # mantém a URL original na interface
                    except Exception as e:
                        LOGGER.error(f"Failed to load local track: {e}")

                # 3. Se não achou no cofre, tenta mirror no SoundCloud
                if not tracks:
                    try:
                        mirror_search = await wavelink.Playable.search(f"scsearch:{title}")
                        if mirror_search:
                            tracks = mirror_search
                            LOGGER.info(f"Found mirror on SoundCloud for {title}")
                    except Exception:
                        pass

        if not tracks:
            await interaction.followup.send(embed=make_error_embed("Nenhuma música encontrada nas fontes normais ou no Drive."))
            return

        if isinstance(tracks, wavelink.Playlist):
            added = tracks.tracks
            await player.queue.put_wait(added)
            embed = make_embed(
                title="🎵 Playlist adicionada à fila",
                description=f"**{tracks.name}**\nFaixas: `{len(added)}`",
                color=Colors.SUCCESS
            )
        else:
            track = tracks[0]
            await player.queue.put_wait(track)
            embed = make_embed(
                title="🎵 Música adicionada à fila",
                description=f"**{discord.utils.escape_markdown(track.title)}**\n⏱️ Duração: `{_duration(track.length // 1000)}`\n🔢 Posição: `{len(player.queue)}`",
                color=Colors.SUCCESS
            )
            if getattr(track, 'artwork', None):
                embed.set_thumbnail(url=track.artwork)

        if not player.playing:
            await player.play(player.queue.get())
            
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="fila", description="Mostra a fila de reprodução.")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("O bot não está tocando música."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        
        lines = []
        if player.current:
            lines.append(f"▶️ **Agora:** {discord.utils.escape_markdown(player.current.title)}")
            
        for index, track in enumerate(list(player.queue)[:10], start=1):
            lines.append(f"`{index}.` {discord.utils.escape_markdown(track.title)} (`{_duration(track.length // 1000)}`)")
            
        if not lines:
            await interaction.response.send_message(embed=make_error_embed("A fila está vazia."), ephemeral=True)
            return
            
        await interaction.response.send_message(
            embed=make_embed(title="🎶 Fila de música", description="\n".join(lines))
        )

    @app_commands.command(name="pausar", description="Pausa a faixa atual.")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("Não estou conectado."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        await player.pause(True)
        await interaction.response.send_message(embed=make_success_embed("Música pausada."))

    @app_commands.command(name="continuar", description="Continua a faixa pausada.")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("Não estou conectado."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        await player.pause(False)
        await interaction.response.send_message(embed=make_success_embed("Reprodução retomada."))

    @app_commands.command(name="pular", description="Pula a faixa atual.")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("Não estou conectado."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        await player.skip(force=True)
        await interaction.response.send_message(embed=make_success_embed("Faixa pulada."))

    @app_commands.command(name="parar", description="Limpa a fila e para a reprodução.")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("Não estou conectado."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        player.queue.clear()
        await player.stop()
        await interaction.response.send_message(embed=make_success_embed("Reprodução e fila encerradas."))

    @app_commands.command(name="sair", description="Desconecta o bot do canal de voz.")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.response.send_message(embed=make_error_embed("Não estou conectado."), ephemeral=True)
            return
            
        player: wavelink.Player = interaction.guild.voice_client # type: ignore
        await player.disconnect()
        await interaction.response.send_message(embed=make_success_embed("Saí do canal de voz."))


async def setup(bot: JanioBot) -> None:
    from janio_bot.services.drive_service import drive_vault_service
    drive_vault_service.start()
    await bot.add_cog(MusicCog(bot))
