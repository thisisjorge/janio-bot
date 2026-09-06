from __future__ import annotations

from janio_bot.cogs.prefix import _command_help, _moderation_help
from janio_bot.config import RuntimeMode


def test_community_help_lists_prefix_commands_without_league() -> None:
    embed = _command_help(RuntimeMode.COMMUNITY)
    rendered = "\n".join(
        [embed.description or "", *(field.value or "" for field in embed.fields)]
    )

    assert "!janio" in rendered
    assert "!pontos saldo" in rendered
    assert "!aposta apostar" in rendered
    assert "!lol build" not in rendered


def test_league_help_lists_prefix_commands_without_betting() -> None:
    embed = _command_help(RuntimeMode.LEAGUE)
    rendered = "\n".join(
        [embed.description or "", *(field.value or "" for field in embed.fields)]
    )

    assert "!lol build" in rendered
    assert "!aposta apostar" not in rendered


def test_moderation_help_documents_quoted_prediction_syntax() -> None:
    embed = _moderation_help(RuntimeMode.COMMUNITY)

    assert embed.description is not None
    assert '!aposta criar "título" "opção A" "opção B" [minutos]' in embed.description
    assert "!pontos dar" in embed.description
