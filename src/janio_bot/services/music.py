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


class MusicExtractor:
    def __init__(
        self, *, max_concurrent_extractions: int = MAX_CONCURRENT_EXTRACTIONS
    ) -> None:
        if max_concurrent_extractions <= 0:
            raise ValueError("max_concurrent_extractions precisa ser maior que zero")
        self._extraction_slots = asyncio.Semaphore(max_concurrent_extractions)

    def validate_query(self, query: str) -> str:
        query = query.strip()
        if not query:
            raise ExternalServiceError("Informe o nome ou link de uma música.")
        parsed = urlparse(query)
        if parsed.scheme:
            if parsed.scheme != "https":
                raise ExternalServiceError("Somente links HTTPS do YouTube são aceitos.")
            hostname = (parsed.hostname or "").casefold()
            if hostname not in ALLOWED_MEDIA_HOSTS:
                raise ExternalServiceError(
                    "Por segurança, o MVP aceita apenas links do YouTube."
                )
            return query
        return f"ytsearch1:{query}"

    async def extract(self, query: str, requested_by: int) -> Track:
        validated = self.validate_query(query)
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
            stream_url = str(info["url"])
            webpage_url = str(info.get("webpage_url") or info.get("original_url") or "")
            if not webpage_url:
                raise ValueError("URL pública ausente")
            self.validate_query(webpage_url)
            if urlparse(stream_url).scheme != "https":
                raise ExternalServiceError("A fonte de áudio precisa usar HTTPS.")
            return Track(
                title=str(info.get("title") or "Faixa sem título"),
                webpage_url=webpage_url,
                stream_url=stream_url,
                duration_seconds=duration,
                requested_by=requested_by,
                resolved_at=time.monotonic(),
            )
        except ExternalServiceError:
            raise
        except Exception as exc:
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
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "default_search": "ytsearch",
            "socket_timeout": 15,
            "retries": 2,
            "extractor_retries": 2,
            "source_address": "0.0.0.0",
        }
        with yt_dlp.YoutubeDL(cast(Any, options)) as downloader:
            info = downloader.extract_info(query, download=False)
        if not isinstance(info, dict):
            raise ValueError("resultado inválido")
        return cast(dict[str, Any], info)
