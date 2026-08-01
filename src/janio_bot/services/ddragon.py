from __future__ import annotations

import asyncio
import difflib
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

import httpx

from janio_bot.errors import ChampionNotFound, ExternalServiceError


def normalize_champion_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_marks.casefold())


@dataclass(frozen=True, slots=True)
class Champion:
    id: str
    key: int
    name: str
    title: str
    version: str
    image_url: str


class DataDragonClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str = "https://ddragon.leagueoflegends.com",
        locale: str = "pt_BR",
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self._lock = asyncio.Lock()
        self._cache_expires_at = 0.0
        self._champions: tuple[Champion, ...] = ()

    async def champions(self) -> tuple[Champion, ...]:
        if self._champions and time.monotonic() < self._cache_expires_at:
            return self._champions
        async with self._lock:
            if self._champions and time.monotonic() < self._cache_expires_at:
                return self._champions
            try:
                version_response = await self.http.get(
                    f"{self.base_url}/api/versions.json", timeout=10
                )
                version_response.raise_for_status()
                versions = version_response.json()
                if not isinstance(versions, list) or not versions:
                    raise ValueError("lista de versões vazia")
                version = str(versions[0])

                champion_response = await self.http.get(
                    f"{self.base_url}/cdn/{version}/data/{self.locale}/champion.json",
                    timeout=10,
                )
                champion_response.raise_for_status()
                payload: Any = champion_response.json()
                champion_data = payload["data"]
                if not isinstance(champion_data, dict):
                    raise ValueError("catálogo de campeões inválido")
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                if self._champions:
                    return self._champions
                raise ExternalServiceError(
                    "Não consegui consultar o catálogo do Data Dragon agora."
                ) from exc

            champions = []
            for entry in champion_data.values():
                champion_id = str(entry["id"])
                champions.append(
                    Champion(
                        id=champion_id,
                        key=int(entry["key"]),
                        name=str(entry["name"]),
                        title=str(entry.get("title", "")),
                        version=version,
                        image_url=(
                            f"{self.base_url}/cdn/{version}/img/champion/{champion_id}.png"
                        ),
                    )
                )
            self._champions = tuple(sorted(champions, key=lambda champion: champion.name))
            self._cache_expires_at = time.monotonic() + 60 * 60
            return self._champions

    async def resolve_champion(self, query: str) -> Champion:
        normalized_query = normalize_champion_name(query)
        if not normalized_query:
            raise ChampionNotFound("Informe o nome de um campeão.")
        champions = await self.champions()
        by_normalized: dict[str, Champion] = {}
        for champion in champions:
            by_normalized[normalize_champion_name(champion.id)] = champion
            by_normalized[normalize_champion_name(champion.name)] = champion

        aliases = {
            "wukong": "monkeyking",
            "macaco": "monkeyking",
            "nunu": "nunu",
            "renata": "renata",
        }
        normalized_query = aliases.get(normalized_query, normalized_query)
        exact = by_normalized.get(normalized_query)
        if exact is not None:
            return exact

        partial = {
            champion
            for key, champion in by_normalized.items()
            if normalized_query in key or key in normalized_query
        }
        if len(partial) == 1:
            return partial.pop()

        close_keys = difflib.get_close_matches(
            normalized_query, list(by_normalized), n=3, cutoff=0.58
        )
        suggestions = []
        for key in close_keys:
            name = by_normalized[key].name
            if name not in suggestions:
                suggestions.append(name)
        suffix = f" Você quis dizer: {', '.join(suggestions)}?" if suggestions else ""
        raise ChampionNotFound(f"Campeão “{query}” não encontrado.{suffix}")
