from __future__ import annotations

import json

import httpx
import pytest

from janio_bot.errors import ExternalServiceError
from janio_bot.services.metabot import MetaBotClient


def valid_response(request: httpx.Request) -> httpx.Response:
    assert request.headers["User-Agent"] == (
        "JanioBot/0.1 (+https://github.com/thisisjorge/janio-bot)"
    )
    payload = {
        "result": {
            "content": [],
            "structuredContent": {
                "kind": "entity",
                "patch": "26.14",
                "imageUrl": "https://ddragon.example/Jinx.png",
                "sections": [
                    {"title": "Core items", "items": ["Grevas", "Runaan", "Gume"]},
                    {"title": "Runes", "items": ["Ritmo Fatal", "Presença de Espírito"]},
                ],
                "cta": {
                    "label": "Ver build",
                    "url": "https://metabot.gg/pt_BR/league/champion/Jinx/build",
                },
                "footnote": "Dados agregados.",
            },
        },
        "jsonrpc": "2.0",
        "id": 1,
    }
    body = f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    return httpx.Response(
        200,
        text=body,
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )


async def test_parses_structured_build_and_attribution_url() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(valid_response)) as http:
        build = await MetaBotClient(http).get_build("Jinx")
    assert build.patch == "26.14"
    assert build.items == ("Grevas", "Runaan", "Gume")
    assert build.runes == ("Ritmo Fatal", "Presença de Espírito")
    assert build.page_url.startswith("https://metabot.gg/")


async def test_rejects_unexpected_attribution_domain() -> None:
    def malicious(_request: httpx.Request) -> httpx.Response:
        response = valid_response(_request)
        body = response.text.replace("https://metabot.gg/", "https://example.invalid/")
        return httpx.Response(200, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(malicious)) as http:
        with pytest.raises(ExternalServiceError):
            await MetaBotClient(http).get_build("Jinx")
