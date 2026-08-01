from __future__ import annotations

import httpx
import pytest

from janio_bot.errors import ChampionNotFound
from janio_bot.services.ddragon import DataDragonClient, normalize_champion_name


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/api/versions.json"):
        return httpx.Response(200, json=["16.14.1"])
    return httpx.Response(
        200,
        json={
            "data": {
                "MonkeyKing": {
                    "id": "MonkeyKing",
                    "key": "62",
                    "name": "Wukong",
                    "title": "o Macaco Rei",
                },
                "Chogath": {
                    "id": "Chogath",
                    "key": "31",
                    "name": "Cho'Gath",
                    "title": "o Terror do Vazio",
                },
            }
        },
    )


async def test_resolves_alias_accents_and_punctuation() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = DataDragonClient(http)
        assert (await client.resolve_champion("wukong")).id == "MonkeyKing"
        assert (await client.resolve_champion("monkey king")).name == "Wukong"
        assert (await client.resolve_champion("cho gath")).id == "Chogath"


async def test_unknown_champion_has_suggestion() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = DataDragonClient(http)
        with pytest.raises(ChampionNotFound) as captured:
            await client.resolve_champion("wukogn")
        assert "Wukong" in str(captured.value)


def test_normalization() -> None:
    assert normalize_champion_name("  K'Santé ") == "ksante"
