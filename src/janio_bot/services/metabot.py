from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from janio_bot.errors import ExternalServiceError


@dataclass(frozen=True, slots=True)
class BuildRecommendation:
    champion_name: str
    patch: str
    items: tuple[str, ...]
    runes: tuple[str, ...]
    page_url: str
    image_url: str | None
    note: str | None


class MetaBotClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        endpoint: str = "https://metabot.gg/api/mcp",
    ) -> None:
        self.http = http
        self.endpoint = endpoint
        self._cache: dict[str, tuple[float, BuildRecommendation]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_build(self, champion_name: str) -> BuildRecommendation:
        cache_key = champion_name.casefold()
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(cache_key)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
            recommendation = await self._request_build(champion_name)
            self._cache[cache_key] = (time.monotonic() + 15 * 60, recommendation)
            return recommendation

    async def _request_build(self, champion_name: str) -> BuildRecommendation:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_entity_build",
                "arguments": {
                    "game": "league",
                    "name": champion_name,
                    "lang": "pt_BR",
                },
            },
        }
        try:
            response = await self.http.post(
                self.endpoint,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "User-Agent": (
                        "JanioBot/0.1 (+https://github.com/thisisjorge/janio-bot)"
                    ),
                },
                json=request,
                timeout=15,
            )
            response.raise_for_status()
            envelope = self._parse_mcp_response(response.text)
            if "error" in envelope:
                raise ValueError(str(envelope["error"]))
            result: Any = envelope["result"]
            if result.get("isError"):
                raise ValueError("a ferramenta retornou erro")
            structured: Any = result["structuredContent"]
            sections = structured.get("sections", [])
            items: tuple[str, ...] = ()
            runes: tuple[str, ...] = ()
            for section in sections:
                title = str(section.get("title", "")).casefold()
                values = tuple(str(item) for item in section.get("items", []))
                if "item" in title:
                    items = values
                elif "rune" in title or "runa" in title:
                    runes = values
            cta = structured["cta"]
            page_url = str(cta["url"])
            if urlparse(page_url).netloc.casefold() not in {
                "metabot.gg",
                "www.metabot.gg",
            }:
                raise ValueError("link de atribuição inesperado")
            if not items and not runes:
                raise ValueError("build vazia")
            recommendation = BuildRecommendation(
                champion_name=champion_name,
                patch=str(structured.get("patch", "?")),
                items=items,
                runes=runes,
                page_url=page_url,
                image_url=(
                    str(structured["imageUrl"]) if structured.get("imageUrl") else None
                ),
                note=str(structured["footnote"]) if structured.get("footnote") else None,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ExternalServiceError(
                "Não consegui consultar a build atual agora. Tente novamente em instantes."
            ) from exc
        return recommendation

    @staticmethod
    def _parse_mcp_response(body: str) -> dict[str, Any]:
        stripped = body.strip()
        if stripped.startswith("{"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                raise ValueError("resposta MCP inválida")
            return parsed
        data_lines = [
            line.removeprefix("data:").strip()
            for line in stripped.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            raise ValueError("evento SSE sem dados")
        parsed = json.loads("\n".join(data_lines))
        if not isinstance(parsed, dict):
            raise ValueError("resposta MCP inválida")
        return parsed
