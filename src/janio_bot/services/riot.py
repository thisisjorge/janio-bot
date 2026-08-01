from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from janio_bot.errors import ExternalServiceError, RiotApiNotConfigured

PLATFORM_TO_CLUSTER = {
    "br1": "americas",
    "na1": "americas",
    "la1": "americas",
    "la2": "americas",
    "oc1": "sea",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

QUEUE_NAMES = {
    "RANKED_SOLO_5x5": "Solo/Duo",
    "RANKED_FLEX_SR": "Flex",
}

PROFILE_CACHE_TTL_SECONDS = 60
PROFILE_CACHE_MAX_ENTRIES = 256
MAX_CONCURRENT_REQUESTS = 4
DEFAULT_RETRY_AFTER_SECONDS = 30
MAX_RETRY_AFTER_SECONDS = 300
RATE_LIMIT_CLOCK_EPSILON_SECONDS = 1e-6

ProfileCacheKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class RankedEntry:
    queue_name: str
    tier: str
    rank: str
    league_points: int
    wins: int
    losses: int


@dataclass(frozen=True, slots=True)
class RiotProfile:
    game_name: str
    tag_line: str
    summoner_level: int
    profile_icon_id: int
    ranks: tuple[RankedEntry, ...]


class RiotClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str | None) -> None:
        self.http = http
        self.api_key = api_key
        self._profile_cache: dict[
            ProfileCacheKey, tuple[float, RiotProfile]
        ] = {}
        self._inflight_profiles: dict[
            ProfileCacheKey, asyncio.Task[RiotProfile]
        ] = {}
        self._profile_state_lock = asyncio.Lock()
        self._request_slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._rate_limit_lock = asyncio.Lock()
        self._rate_limited_until = 0.0

    async def get_profile(
        self, game_name: str, tag_line: str, *, platform: str = "br1"
    ) -> RiotProfile:
        if not self.api_key:
            raise RiotApiNotConfigured(
                "Defina RIOT_API_KEY no .env para usar a consulta de jogador."
            )
        platform = platform.casefold()
        cluster = PLATFORM_TO_CLUSTER.get(platform)
        if cluster is None:
            raise ExternalServiceError(f"Região não suportada: {platform}.")
        game_name = game_name.strip()
        tag_line = tag_line.strip()
        if not game_name or not tag_line:
            raise ExternalServiceError("Informe o nome e a tag do Riot ID.")

        cache_key = (platform, game_name.casefold(), tag_line.casefold())
        async with self._profile_state_lock:
            now = time.monotonic()
            cached = self._profile_cache.get(cache_key)
            if cached is not None:
                if cached[0] > now:
                    return cached[1]
                del self._profile_cache[cache_key]

            task = self._inflight_profiles.get(cache_key)
            if task is None:
                task = asyncio.create_task(
                    self._fetch_and_cache_profile(
                        cache_key,
                        game_name,
                        tag_line,
                        platform,
                        cluster,
                    )
                )
                self._inflight_profiles[cache_key] = task
        return await asyncio.shield(task)

    async def _fetch_and_cache_profile(
        self,
        cache_key: ProfileCacheKey,
        game_name: str,
        tag_line: str,
        platform: str,
        cluster: str,
    ) -> RiotProfile:
        try:
            profile = await self._fetch_profile(
                game_name,
                tag_line,
                platform=platform,
                cluster=cluster,
            )
            async with self._profile_state_lock:
                now = time.monotonic()
                self._prune_profile_cache(now)
                if len(self._profile_cache) >= PROFILE_CACHE_MAX_ENTRIES:
                    oldest_key = min(
                        self._profile_cache,
                        key=lambda key: self._profile_cache[key][0],
                    )
                    del self._profile_cache[oldest_key]
                self._profile_cache[cache_key] = (
                    now + PROFILE_CACHE_TTL_SECONDS,
                    profile,
                )
            return profile
        finally:
            current_task = asyncio.current_task()
            async with self._profile_state_lock:
                if self._inflight_profiles.get(cache_key) is current_task:
                    del self._inflight_profiles[cache_key]

    def _prune_profile_cache(self, now: float) -> None:
        expired = [
            key for key, (expires_at, _) in self._profile_cache.items()
            if expires_at <= now
        ]
        for key in expired:
            del self._profile_cache[key]

    async def _fetch_profile(
        self,
        game_name: str,
        tag_line: str,
        *,
        platform: str,
        cluster: str,
    ) -> RiotProfile:
        assert self.api_key is not None
        headers = {"X-Riot-Token": self.api_key}

        account = await self._get_json(
            (
                f"https://{cluster}.api.riotgames.com/riot/account/v1/accounts/"
                f"by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
            ),
            headers,
        )
        puuid = str(account["puuid"])
        summoner_url = (
            f"https://{platform}.api.riotgames.com/lol/summoner/v4/"
            f"summoners/by-puuid/{quote(puuid, safe='')}"
        )
        ranks_url = (
            f"https://{platform}.api.riotgames.com/lol/league/v4/"
            f"entries/by-puuid/{quote(puuid, safe='')}"
        )
        summoner, league_entries = await asyncio.gather(
            self._get_json(summoner_url, headers),
            self._get_json(ranks_url, headers),
        )
        if not isinstance(league_entries, list):
            raise ExternalServiceError("A Riot retornou um formato de rank inesperado.")
        ranks = tuple(
            RankedEntry(
                queue_name=QUEUE_NAMES.get(
                    str(entry.get("queueType")), str(entry.get("queueType", "Ranqueada"))
                ),
                tier=str(entry.get("tier", "UNRANKED")),
                rank=str(entry.get("rank", "")),
                league_points=int(entry.get("leaguePoints", 0)),
                wins=int(entry.get("wins", 0)),
                losses=int(entry.get("losses", 0)),
            )
            for entry in league_entries
            if entry.get("queueType") in QUEUE_NAMES
        )
        return RiotProfile(
            game_name=str(account.get("gameName", game_name)),
            tag_line=str(account.get("tagLine", tag_line)),
            summoner_level=int(summoner.get("summonerLevel", 0)),
            profile_icon_id=int(summoner.get("profileIconId", 0)),
            ranks=ranks,
        )

    async def _get_json(self, url: str, headers: dict[str, str]) -> Any:
        async with self._request_slots:
            await self._raise_if_rate_limited()
            try:
                response = await self.http.get(
                    url,
                    headers=headers,
                    timeout=12,
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                raise ExternalServiceError(
                    "A API da Riot demorou demais para responder."
                ) from exc
            except httpx.HTTPError as exc:
                raise ExternalServiceError("Não consegui conectar à API da Riot.") from exc
            if response.status_code == 429:
                retry_after = self._parse_retry_after(
                    response.headers.get("Retry-After")
                )
                retry_after = await self._record_rate_limit(retry_after)
                raise self._rate_limit_error(retry_after)

        if response.status_code == 404:
            raise ExternalServiceError("Jogador não encontrado. Confira o Riot ID e a tag.")
        if response.status_code in {401, 403}:
            raise ExternalServiceError(
                "A chave da Riot é inválida ou expirou. Atualize RIOT_API_KEY."
            )
        try:
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ExternalServiceError(
                f"A API da Riot respondeu com erro ({response.status_code})."
            ) from exc

    async def _raise_if_rate_limited(self) -> None:
        async with self._rate_limit_lock:
            remaining = self._rate_limited_until - time.monotonic()
        if remaining > 0:
            raise self._rate_limit_error(self._ceil_retry_after(remaining))

    async def _record_rate_limit(self, retry_after: int) -> int:
        async with self._rate_limit_lock:
            now = time.monotonic()
            self._rate_limited_until = max(
                self._rate_limited_until,
                now + retry_after,
            )
            return self._ceil_retry_after(self._rate_limited_until - now)

    @staticmethod
    def _ceil_retry_after(remaining: float) -> int:
        return max(
            1,
            math.ceil(remaining - RATE_LIMIT_CLOCK_EPSILON_SECONDS),
        )

    @staticmethod
    def _parse_retry_after(raw_value: str | None) -> int:
        try:
            retry_after = int(raw_value) if raw_value is not None else 0
        except ValueError:
            retry_after = 0
        if retry_after <= 0:
            return DEFAULT_RETRY_AFTER_SECONDS
        return min(retry_after, MAX_RETRY_AFTER_SECONDS)

    @staticmethod
    def _rate_limit_error(retry_after: int) -> ExternalServiceError:
        return ExternalServiceError(
            "Limite da API da Riot atingido. "
            f"Tente novamente em {retry_after} segundos."
        )
