from __future__ import annotations

import asyncio

import httpx
import pytest

from janio_bot.errors import ExternalServiceError, RiotApiNotConfigured
from janio_bot.services.riot import RiotClient


def riot_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-Riot-Token"] == "secret"
    if "/riot/account/" in request.url.path:
        assert request.url.host == "americas.api.riotgames.com"
        return httpx.Response(
            200,
            json={"puuid": "p-123", "gameName": "Jogador", "tagLine": "BR1"},
        )
    if "/summoner/" in request.url.path:
        assert request.url.host == "br1.api.riotgames.com"
        return httpx.Response(
            200, json={"summonerLevel": 250, "profileIconId": 1234}
        )
    assert "/league/" in request.url.path
    return httpx.Response(
        200,
        json=[
            {
                "queueType": "RANKED_SOLO_5x5",
                "tier": "GOLD",
                "rank": "II",
                "leaguePoints": 75,
                "wins": 10,
                "losses": 5,
            }
        ],
    )


async def test_br_profile_uses_americas_and_br1_routes() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(riot_handler)) as http:
        profile = await RiotClient(http, "secret").get_profile(
            "Jogador", "BR1", platform="br1"
        )
    assert profile.game_name == "Jogador"
    assert profile.summoner_level == 250
    assert profile.ranks[0].wins == 10


async def test_missing_key_is_explicit() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(riot_handler)) as http:
        with pytest.raises(RiotApiNotConfigured):
            await RiotClient(http, None).get_profile("Jogador", "BR1")


async def test_riot_429_reports_retry_after() -> None:
    requests = 0

    def limited(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(429, headers={"Retry-After": "12"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited)) as http:
        client = RiotClient(http, "secret")
        with pytest.raises(ExternalServiceError, match="12"):
            await client.get_profile("Jogador", "BR1")
        with pytest.raises(ExternalServiceError, match="1[12]"):
            await client.get_profile("Outro", "BR1")
    assert requests == 1


async def test_identical_profile_requests_are_coalesced_and_cached() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        await asyncio.sleep(0)
        return riot_handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RiotClient(http, "secret")
        first, second = await asyncio.gather(
            client.get_profile("Jogador", "BR1"),
            client.get_profile("jogador", "br1"),
        )
        cached = await client.get_profile(" JOGADOR ", " BR1 ")

    assert first == second == cached
    assert len(requests) == 3


async def test_token_is_not_forwarded_through_redirects() -> None:
    hosts: list[str] = []

    def redirecting(request: httpx.Request) -> httpx.Response:
        hosts.append(str(request.url.host))
        if request.url.host != "americas.api.riotgames.com":
            pytest.fail("A requisição seguiu o redirect com o token da Riot.")
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.invalid/capture"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(redirecting),
        follow_redirects=True,
    ) as http:
        with pytest.raises(ExternalServiceError, match="302"):
            await RiotClient(http, "secret").get_profile("Jogador", "BR1")

    assert hosts == ["americas.api.riotgames.com"]


@pytest.mark.parametrize(
    ("header_value", "expected_seconds"),
    [
        ("valor-invalido", 30),
        ("999999999999999999999", 300),
    ],
)
async def test_retry_after_is_sanitized_and_bounded(
    header_value: str,
    expected_seconds: int,
) -> None:
    def limited(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": header_value})

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited)) as http:
        with pytest.raises(ExternalServiceError) as captured:
            await RiotClient(http, "secret").get_profile("Jogador", "BR1")

    message = str(captured.value)
    assert str(expected_seconds) in message
    assert header_value not in message
