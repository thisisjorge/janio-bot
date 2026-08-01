from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any, cast

import discord
import pytest

from janio_bot.cogs.music import (
    MAX_QUEUED_TRACKS,
    REQUEST_COOLDOWN_SECONDS,
    GuildMusicState,
    MusicCog,
)
from janio_bot.errors import ExternalServiceError
from janio_bot.services.music import MusicExtractor, Track


def media_info(*, duration: int | None = 180, is_live: bool = False) -> dict[str, Any]:
    return {
        "title": "Faixa",
        "url": "https://media.example/audio",
        "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "duration": duration,
        "is_live": is_live,
    }


def test_search_terms_are_converted_to_single_result_search() -> None:
    extractor = MusicExtractor()
    assert extractor.validate_query("Daft Punk One More Time") == (
        "ytsearch1:Daft Punk One More Time"
    )


def test_youtube_urls_are_allowed() -> None:
    extractor = MusicExtractor()
    url = "https://www.youtube.com/watch?v=abc"
    assert extractor.validate_query(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://www.youtube.com/watch?v=abcdefghijk",
        "https://example.com/audio.mp3",
    ],
)
def test_arbitrary_urls_are_rejected(url: str) -> None:
    with pytest.raises(ExternalServiceError):
        MusicExtractor().validate_query(url)


@pytest.mark.parametrize(
    "info",
    [
        media_info(duration=None),
        media_info(duration=180, is_live=True),
    ],
)
async def test_live_or_unknown_duration_media_is_rejected(
    monkeypatch: pytest.MonkeyPatch, info: dict[str, Any]
) -> None:
    extractor = MusicExtractor()
    monkeypatch.setattr(extractor, "_extract_sync", lambda _query: info)

    with pytest.raises(ExternalServiceError, match="duração conhecida"):
        await extractor.extract("faixa", requested_by=1)


async def test_extraction_concurrency_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = MusicExtractor(max_concurrent_extractions=1)
    first_started = threading.Event()
    release_first = threading.Event()
    counter_lock = threading.Lock()
    calls = 0

    def extract_sync(_query: str) -> dict[str, Any]:
        nonlocal calls
        with counter_lock:
            calls += 1
            current_call = calls
        if current_call == 1:
            first_started.set()
            release_first.wait(timeout=2)
        return media_info()

    monkeypatch.setattr(extractor, "_extract_sync", extract_sync)
    first = asyncio.create_task(extractor.extract("primeira", requested_by=1))
    tasks = [first]
    try:
        assert await asyncio.to_thread(first_started.wait, 1)
        second = asyncio.create_task(extractor.extract("segunda", requested_by=2))
        tasks.append(second)
        await asyncio.sleep(0.05)
        with counter_lock:
            assert calls == 1
    finally:
        release_first.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert calls == 2


async def test_queue_reservations_are_bounded_under_concurrency() -> None:
    cog = MusicCog(cast(Any, None))
    state = GuildMusicState()

    results = await asyncio.gather(
        *(
            cog._reserve_queue_slot(state, user_id, now=100.0)
            for user_id in range(MAX_QUEUED_TRACKS + 1)
        ),
        return_exceptions=True,
    )

    assert sum(type(result) is int for result in results) == MAX_QUEUED_TRACKS
    assert sum(isinstance(result, ExternalServiceError) for result in results) == 1
    assert len(state.queue_reservations) == MAX_QUEUED_TRACKS

    generation = state.generation
    await cog._clear_state(state)

    assert not state.queue_reservations
    assert state.generation == generation + 1


async def test_request_cooldown_is_scoped_to_user_and_guild() -> None:
    cog = MusicCog(cast(Any, None))
    first_guild = GuildMusicState()
    second_guild = GuildMusicState()

    reservation = await cog._reserve_queue_slot(first_guild, 42, now=100.0)
    await cog._release_queue_slot(first_guild, reservation)

    with pytest.raises(ExternalServiceError, match="Aguarde"):
        await cog._reserve_queue_slot(first_guild, 42, now=101.0)

    await cog._reserve_queue_slot(second_guild, 42, now=101.0)
    await cog._reserve_queue_slot(
        first_guild,
        42,
        now=100.0 + REQUEST_COOLDOWN_SECONDS,
    )


async def test_voice_play_failure_clears_current_and_cleans_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    track = Track(
        title="Faixa",
        webpage_url="https://www.youtube.com/watch?v=abcdefghijk",
        stream_url="https://media.example/audio",
        duration_seconds=180,
        requested_by=1,
        resolved_at=0.0,
    )

    class Extractor:
        async def refresh(self, current: Track) -> Track:
            return current

    class Source:
        cleaned = False

        def cleanup(self) -> None:
            self.cleaned = True

    class Voice:
        def is_playing(self) -> bool:
            return False

        def is_paused(self) -> bool:
            return False

        def play(self, _source: object, *, after: object) -> None:
            raise discord.ClientException("Not connected to voice.")

    source = Source()
    monkeypatch.setattr(discord, "FFmpegPCMAudio", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        discord,
        "PCMVolumeTransformer",
        lambda *_args, **_kwargs: source,
    )
    bot = SimpleNamespace(
        music_extractor=Extractor(),
        settings=SimpleNamespace(ffmpeg_path="ffmpeg"),
        get_channel=lambda _channel_id: None,
    )
    cog = MusicCog(cast(Any, bot))
    state = cog._state(1)
    state.queue.append(track)

    await cog._start_next(1, cast(Any, Voice()))

    assert state.current is None
    assert source.cleaned is True
    assert not state.queue
    assert state.idle_task is not None
    state.idle_task.cancel()
    await asyncio.gather(state.idle_task, return_exceptions=True)
