from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse

import yt_dlp

from janio_bot.errors import ExternalServiceError

ALLOWED_MEDIA_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "soundcloud.com",
    "m.soundcloud.com",
}
MAX_TRACK_SECONDS = 3 * 60 * 60
MAX_CONCURRENT_EXTRACTIONS = 2


@dataclass(frozen=True, slots=True)
class Track:
    title: str
    webpage_url: str
    stream_url: str
    duration_seconds: int | None
    requested_by: int
    resolved_at: float
    thumbnail_url: str | None = None
    http_headers: dict[str, str] | None = None

    artist: str | None = None

class MusicExtractor:
    def __init__(
        self, *, max_concurrent_extractions: int = MAX_CONCURRENT_EXTRACTIONS
    ) -> None:
        if max_concurrent_extractions <= 0:
            raise ValueError("max_concurrent_extractions precisa ser maior que zero")
        self._extraction_slots = asyncio.Semaphore(max_concurrent_extractions)

    async def validate_query(self, query: str) -> str:
        query = query.strip()
        if not query:
            raise ExternalServiceError("Informe o nome ou link de uma música.")
        parsed = urlparse(query)
        if parsed.scheme:
            if parsed.scheme != "https":
                raise ExternalServiceError("Somente links HTTPS do YouTube são aceitos.")
            hostname = (parsed.hostname or "").casefold()
            
            if "spotify.com" in hostname:
                import aiohttp
                import json
                try:
                    oembed_url = f"https://open.spotify.com/oembed?url={query}"
                    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
                        async with session.get(oembed_url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                title = data.get("title")
                                if title:
                                    return f"scsearch:{title}"
                            else:
                                # Fallback: regex
                                async with session.get(query) as resp2:
                                    html = await resp2.text()
                                    import re
                                    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                                    if match and match.group(1).strip() != "Spotify":
                                        full_title = match.group(1).replace(" | Spotify", "")
                                        return f"scsearch:{full_title}"
                except Exception:
                    pass
                raise ExternalServiceError("O Spotify bloqueou a leitura desta música. Busque pelo nome da música em vez do link!")

            if hostname not in ALLOWED_MEDIA_HOSTS:
                raise ExternalServiceError(
                    "Por segurança, o MVP aceita apenas links do YouTube, SoundCloud e Spotify."
                )
            return query
        return f"scsearch:{query}"

    async def extract(self, query: str, requested_by: int) -> Track:
        validated = await self.validate_query(query)
        try:
            info = await self._extract_limited(validated)
            if entries := info.get("entries"):
                selected = next(
                    (entry for entry in entries if isinstance(entry, dict)), None
                )
                if selected is None:
                    raise ValueError("nenhum resultado")
                info = selected
            duration_raw = info.get("duration")
            live_status = str(info.get("live_status") or "").casefold()
            if (
                info.get("is_live") is True
                or live_status in {"is_live", "is_upcoming"}
                or duration_raw is None
            ):
                raise ExternalServiceError(
                    "Transmissões ao vivo ou faixas sem duração conhecida não são aceitas."
                )
            duration = int(duration_raw)
            if duration <= 0:
                raise ExternalServiceError(
                    "Transmissões ao vivo ou faixas sem duração conhecida não são aceitas."
                )
            if duration > MAX_TRACK_SECONDS:
                raise ExternalServiceError("A faixa pode ter no máximo 3 horas.")
            
            stream_url = info.get("url")
            if not stream_url and "formats" in info:
                # Find best audio format manually
                audio_formats = [f for f in info["formats"] if f.get("vcodec") == "none" and f.get("acodec") != "none"]
                if audio_formats:
                    # Sort by abr (audio bitrate) descending
                    audio_formats.sort(key=lambda x: x.get("abr") or 0, reverse=True)
                    stream_url = audio_formats[0].get("url")
                else:
                    # Fallback to any format with audio
                    formats = [f for f in info["formats"] if f.get("acodec") != "none"]
                    if formats:
                        stream_url = formats[-1].get("url")

            stream_url = str(stream_url or "")
            webpage_url = str(info.get("webpage_url") or info.get("original_url") or "")
            if not webpage_url:
                raise ValueError("URL pública ausente")
            await self.validate_query(webpage_url)
            if urlparse(stream_url).scheme != "https":
                raise ExternalServiceError("A fonte de áudio precisa usar HTTPS.")
            return Track(
                title=str(info.get("title") or "Faixa sem título"),
                webpage_url=webpage_url,
                stream_url=stream_url,
                duration_seconds=duration,
                requested_by=requested_by,
                resolved_at=time.monotonic(),
                thumbnail_url=info.get("thumbnail"),
                http_headers=info.get("http_headers"),
                artist=str(info.get("artist") or info.get("uploader") or ""),
            )
        except ExternalServiceError as exc:
            print("ExternalServiceError:", exc)
            raise
        except Exception as exc:
            import traceback
            traceback.print_exc()
            raise ExternalServiceError(
                "Não consegui localizar ou abrir essa faixa."
            ) from exc

    async def _extract_limited(self, query: str) -> dict[str, Any]:
        await self._extraction_slots.acquire()
        try:
            extraction = asyncio.create_task(asyncio.to_thread(self._extract_sync, query))
        except BaseException:
            self._extraction_slots.release()
            raise
        extraction.add_done_callback(self._release_extraction_slot)
        return await asyncio.shield(extraction)

    def _release_extraction_slot(
        self, _extraction: asyncio.Future[dict[str, Any]]
    ) -> None:
        self._extraction_slots.release()
        if not _extraction.cancelled():
            _extraction.exception()

    async def refresh(self, track: Track) -> Track:
        if time.monotonic() - track.resolved_at < 5 * 60:
            return track
        return await self.extract(track.webpage_url, track.requested_by)

    @staticmethod
    def _extract_sync(query: str) -> dict[str, Any]:
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "default_search": "scsearch",
            "socket_timeout": 15,
            "retries": 2,
            "extractor_retries": 2,
            "source_address": "0.0.0.0",
            "extractor_args": {"youtube": {"player_client": ["web", "ios", "android"]}},
        }
        import os
        if os.path.exists("cookies.txt"):
            options["cookiefile"] = "cookies.txt"
        with yt_dlp.YoutubeDL(cast(Any, options)) as downloader:
            info = downloader.extract_info(query, download=False)
        if not isinstance(info, dict):
            raise ValueError("resultado inválido")
        return cast(dict[str, Any], info)
