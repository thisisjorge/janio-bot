from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from janio_bot.cogs.betting import (
    EMBED_DESCRIPTION_LIMIT,
    market_embed,
    open_markets_description,
)
from janio_bot.database import Database
from janio_bot.errors import (
    AlreadyBet,
    DailyAlreadyClaimed,
    InsufficientPoints,
    MarketNotFound,
    MarketUnavailable,
)
from janio_bot.models import BetReceipt, MarketStatus


@pytest.fixture
async def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "janio.sqlite3", default_points=1000, daily_points=250)
    await db.initialize()
    return db


async def create_market(database: Database, *, guild_id: int = 1, now: int = 1000) -> int:
    market = await database.create_market(
        guild_id,
        channel_id=10,
        created_by=99,
        title="Time azul vence?",
        option_a="Sim",
        option_b="Não",
        duration_minutes=10,
        now=now,
    )
    return market.id


async def test_wallet_starts_with_configured_points(database: Database) -> None:
    assert await database.get_balance(1, 42, now=100) == 1000


async def test_daily_can_only_be_claimed_once_per_day(database: Database) -> None:
    assert await database.claim_daily(1, 42, now=100) == 1250
    with pytest.raises(DailyAlreadyClaimed) as captured:
        await database.claim_daily(1, 42, now=101)
    assert captured.value.retry_after_seconds == 86_399
    assert await database.claim_daily(1, 42, now=86_500) == 1500


async def test_bet_debits_wallet_and_rejects_second_bet(database: Database) -> None:
    market_id = await create_market(database)
    receipt = await database.place_bet(1, 42, market_id, "A", 300, now=1001)
    assert receipt == BetReceipt(
        market_id=market_id, option="A", amount=300, new_balance=700
    )
    with pytest.raises(AlreadyBet):
        await database.place_bet(1, 42, market_id, "B", 100, now=1002)
    assert await database.get_balance(1, 42, now=1003) == 700


async def test_insufficient_points_never_makes_balance_negative(database: Database) -> None:
    market_id = await create_market(database)
    with pytest.raises(InsufficientPoints):
        await database.place_bet(1, 42, market_id, "A", 1001, now=1001)
    assert await database.get_balance(1, 42, now=1002) == 1000


async def test_settlement_distributes_entire_pool_with_integer_remainder(
    database: Database,
) -> None:
    market_id = await create_market(database)
    await database.place_bet(1, 1, market_id, "A", 100, now=1001)
    await database.place_bet(1, 2, market_id, "A", 200, now=1001)
    await database.place_bet(1, 3, market_id, "B", 700, now=1001)

    result = await database.settle_market(1, market_id, "A", now=1002)

    assert result.total_pool == 1000
    assert result.winning_pool == 300
    assert sum(payout.amount for payout in result.payouts) == 1000
    assert {payout.user_id: payout.amount for payout in result.payouts} == {
        1: 333,
        2: 667,
    }
    assert await database.get_balance(1, 1, now=1003) == 1233
    assert await database.get_balance(1, 2, now=1003) == 1467
    assert await database.get_balance(1, 3, now=1003) == 300
    assert (
        await database.get_balance(1, 1, now=1003)
        + await database.get_balance(1, 2, now=1003)
        + await database.get_balance(1, 3, now=1003)
        == 3000
    )


async def test_no_winners_refunds_every_bet(database: Database) -> None:
    market_id = await create_market(database)
    await database.place_bet(1, 1, market_id, "B", 400, now=1001)
    await database.place_bet(1, 2, market_id, "B", 600, now=1001)

    result = await database.settle_market(1, market_id, "A", now=1002)

    assert result.refunded_because_no_winners is True
    assert sum(payout.amount for payout in result.payouts) == 1000
    assert await database.get_balance(1, 1, now=1003) == 1000
    assert await database.get_balance(1, 2, now=1003) == 1000


async def test_cancel_refunds_and_cannot_run_twice(database: Database) -> None:
    market_id = await create_market(database)
    await database.place_bet(1, 1, market_id, "A", 250, now=1001)
    result = await database.cancel_market(1, market_id, now=1002)
    assert result.total_refunded == 250
    assert await database.get_balance(1, 1, now=1003) == 1000
    with pytest.raises(MarketUnavailable):
        await database.cancel_market(1, market_id, now=1004)


async def test_closed_and_expired_markets_reject_bets(database: Database) -> None:
    market_id = await create_market(database)
    await database.close_market(1, market_id, now=1001)
    with pytest.raises(MarketUnavailable):
        await database.place_bet(1, 1, market_id, "A", 100, now=1002)

    expiring = await database.create_market(
        1,
        10,
        99,
        "Expira",
        "A",
        "B",
        duration_minutes=1,
        now=2000,
    )
    expired = await database.close_expired_markets(now=2060)
    assert (1, expiring.id) in expired
    assert (await database.get_market(1, expiring.id)).status is MarketStatus.CLOSED


async def test_concurrent_spending_is_serialized(database: Database) -> None:
    first = await create_market(database, now=1000)
    second = await create_market(database, now=1000)
    results = await asyncio.gather(
        database.place_bet(1, 55, first, "A", 800, now=1001),
        database.place_bet(1, 55, second, "B", 800, now=1001),
        return_exceptions=True,
    )
    assert sum(isinstance(result, BetReceipt) for result in results) == 1
    assert sum(isinstance(result, InsufficientPoints) for result in results) == 1
    assert await database.get_balance(1, 55, now=1002) == 200


async def test_guild_balances_and_markets_are_isolated(database: Database) -> None:
    market_id = await create_market(database, guild_id=1)
    with pytest.raises(MarketNotFound):
        await database.place_bet(2, 42, market_id, "A", 100, now=1001)
    assert await database.get_balance(2, 42, now=1002) == 1000


async def test_announcement_is_claimed_only_when_due(database: Database) -> None:
    await database.configure_announcement(
        1, 10, "mensagem", 210, now=1000
    )
    assert await database.claim_due_announcements(now=1209) == ()
    due = await database.claim_due_announcements(now=1210)
    assert len(due) == 1
    assert due[0].message == "mensagem"
    assert await database.claim_due_announcements(now=1211) == ()
    assert len(await database.claim_due_announcements(now=1420)) == 1


async def test_market_embed_only_shows_betting_cta_while_open(database: Database) -> None:
    market_id = await create_market(database)
    open_snapshot = await database.get_market_snapshot(1, market_id)
    assert "/aposta apostar" in str(market_embed(open_snapshot).description)

    await database.close_market(1, market_id, now=1002)
    closed_snapshot = await database.get_market_snapshot(1, market_id)
    assert "/aposta apostar" not in str(market_embed(closed_snapshot).description)
    assert "encerradas" in str(market_embed(closed_snapshot).description)


async def test_open_markets_description_stays_within_embed_limit(
    database: Database,
) -> None:
    snapshots = []
    for index in range(20):
        market = await database.create_market(
            1,
            channel_id=10,
            created_by=99,
            title=f"{index} " + "T" * 148,
            option_a="A" * 80,
            option_b="B" * 80,
            duration_minutes=10,
            now=1000 + index,
        )
        snapshots.append(await database.get_market_snapshot(1, market.id))

    description = open_markets_description(snapshots)
    assert len(description) <= EMBED_DESCRIPTION_LIMIT
    assert "… e mais" in description
