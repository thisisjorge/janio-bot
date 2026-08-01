from __future__ import annotations

import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from janio_bot.errors import (
    AlreadyBet,
    DailyAlreadyClaimed,
    InsufficientPoints,
    InvalidBet,
    MarketNotFound,
    MarketUnavailable,
)
from janio_bot.models import (
    AnnouncementSetting,
    BetReceipt,
    Cancellation,
    LeaderboardEntry,
    Market,
    MarketSnapshot,
    MarketStatus,
    Settlement,
    UserPayout,
)

SECONDS_PER_DAY = 24 * 60 * 60

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wallets (
    guild_id       INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    balance        INTEGER NOT NULL CHECK (balance >= 0),
    last_daily_at  INTEGER,
    created_at     INTEGER NOT NULL,
    updated_at     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS markets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    channel_id      INTEGER NOT NULL,
    message_id      INTEGER,
    title           TEXT NOT NULL,
    option_a        TEXT NOT NULL,
    option_b        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (
                        status IN ('OPEN', 'CLOSED', 'SETTLED', 'CANCELLED')
                    ),
    created_by      INTEGER NOT NULL,
    created_at      INTEGER NOT NULL,
    closes_at       INTEGER,
    closed_at       INTEGER,
    resolved_at     INTEGER,
    winning_option  TEXT CHECK (winning_option IN ('A', 'B') OR winning_option IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_markets_guild_status
    ON markets (guild_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS bets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   INTEGER NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    option_key  TEXT NOT NULL CHECK (option_key IN ('A', 'B')),
    amount      INTEGER NOT NULL CHECK (amount > 0),
    created_at  INTEGER NOT NULL,
    UNIQUE (market_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_bets_market_option
    ON bets (market_id, option_key);

CREATE TABLE IF NOT EXISTS points_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    delta           INTEGER NOT NULL,
    balance_after   INTEGER NOT NULL CHECK (balance_after >= 0),
    reason          TEXT NOT NULL,
    reference_type  TEXT,
    reference_id    INTEGER,
    created_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_user
    ON points_ledger (guild_id, user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id                       INTEGER PRIMARY KEY,
    announcement_channel_id        INTEGER NOT NULL,
    announcement_message           TEXT NOT NULL,
    announcement_interval_seconds  INTEGER NOT NULL CHECK (
                                       announcement_interval_seconds >= 30
                                   ),
    announcement_enabled           INTEGER NOT NULL DEFAULT 1 CHECK (
                                       announcement_enabled IN (0, 1)
                                   ),
    last_announcement_attempt_at    INTEGER,
    updated_at                      INTEGER NOT NULL
);

PRAGMA user_version = 1;
"""


class Database:
    def __init__(self, path: Path, *, default_points: int, daily_points: int) -> None:
        self.path = path
        self.default_points = default_points
        self.daily_points = daily_points

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as connection:
            await connection.execute("PRAGMA journal_mode = WAL")
            await connection.executescript(SCHEMA)
            await connection.commit()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path, timeout=10)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            await connection.close()

    @staticmethod
    def _now(now: int | None = None) -> int:
        return int(time.time()) if now is None else now

    async def _ensure_wallet(
        self,
        connection: aiosqlite.Connection,
        guild_id: int,
        user_id: int,
        now: int,
    ) -> None:
        cursor = await connection.execute(
            """
            INSERT OR IGNORE INTO wallets (
                guild_id, user_id, balance, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, self.default_points, now, now),
        )
        if cursor.rowcount:
            await connection.execute(
                """
                INSERT INTO points_ledger (
                    guild_id, user_id, delta, balance_after, reason,
                    reference_type, created_at
                ) VALUES (?, ?, ?, ?, 'Saldo inicial', 'wallet', ?)
                """,
                (guild_id, user_id, self.default_points, self.default_points, now),
            )

    async def get_balance(self, guild_id: int, user_id: int, *, now: int | None = None) -> int:
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await self._ensure_wallet(connection, guild_id, user_id, timestamp)
            cursor = await connection.execute(
                "SELECT balance FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            await connection.commit()
        assert row is not None
        return int(row["balance"])

    async def claim_daily(
        self, guild_id: int, user_id: int, *, now: int | None = None
    ) -> int:
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await self._ensure_wallet(connection, guild_id, user_id, timestamp)
            cursor = await connection.execute(
                """
                SELECT balance, last_daily_at
                FROM wallets
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            assert row is not None
            last_daily_at = row["last_daily_at"]
            if last_daily_at is not None:
                elapsed = timestamp - int(last_daily_at)
                if elapsed < SECONDS_PER_DAY:
                    await connection.rollback()
                    raise DailyAlreadyClaimed(SECONDS_PER_DAY - elapsed)

            new_balance = int(row["balance"]) + self.daily_points
            await connection.execute(
                """
                UPDATE wallets
                SET balance = ?, last_daily_at = ?, updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (new_balance, timestamp, timestamp, guild_id, user_id),
            )
            await connection.execute(
                """
                INSERT INTO points_ledger (
                    guild_id, user_id, delta, balance_after, reason,
                    reference_type, created_at
                ) VALUES (?, ?, ?, ?, 'Resgate diário', 'daily', ?)
                """,
                (guild_id, user_id, self.daily_points, new_balance, timestamp),
            )
            await connection.commit()
        return new_balance

    async def adjust_points(
        self,
        guild_id: int,
        user_id: int,
        delta: int,
        *,
        reason: str,
        actor_id: int,
        now: int | None = None,
    ) -> int:
        if delta == 0:
            raise InvalidBet("O ajuste precisa ser diferente de zero.")
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await self._ensure_wallet(connection, guild_id, user_id, timestamp)
            cursor = await connection.execute(
                "SELECT balance FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            assert row is not None
            new_balance = int(row["balance"]) + delta
            if new_balance < 0:
                await connection.rollback()
                raise InsufficientPoints("O saldo não pode ficar negativo.")
            await connection.execute(
                """
                UPDATE wallets SET balance = ?, updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (new_balance, timestamp, guild_id, user_id),
            )
            await connection.execute(
                """
                INSERT INTO points_ledger (
                    guild_id, user_id, delta, balance_after, reason,
                    reference_type, reference_id, created_at
                ) VALUES (?, ?, ?, ?, ?, 'admin', ?, ?)
                """,
                (guild_id, user_id, delta, new_balance, reason, actor_id, timestamp),
            )
            await connection.commit()
        return new_balance

    async def leaderboard(self, guild_id: int, *, limit: int = 10) -> tuple[LeaderboardEntry, ...]:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT user_id, balance
                FROM wallets
                WHERE guild_id = ?
                ORDER BY balance DESC, user_id ASC
                LIMIT ?
                """,
                (guild_id, limit),
            )
            rows = await cursor.fetchall()
        return tuple(
            LeaderboardEntry(user_id=int(row["user_id"]), balance=int(row["balance"]))
            for row in rows
        )

    async def create_market(
        self,
        guild_id: int,
        channel_id: int,
        created_by: int,
        title: str,
        option_a: str,
        option_b: str,
        *,
        duration_minutes: int | None,
        now: int | None = None,
    ) -> Market:
        timestamp = self._now(now)
        title = title.strip()
        option_a = option_a.strip()
        option_b = option_b.strip()
        if not title or not option_a or not option_b:
            raise InvalidBet("Título e opções não podem ficar vazios.")
        if option_a.casefold() == option_b.casefold():
            raise InvalidBet("As duas opções precisam ser diferentes.")
        if duration_minutes is not None and not 1 <= duration_minutes <= 1440:
            raise InvalidBet("A duração precisa ficar entre 1 e 1440 minutos.")
        closes_at = (
            timestamp + duration_minutes * 60 if duration_minutes is not None else None
        )

        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO markets (
                    guild_id, channel_id, title, option_a, option_b, status,
                    created_by, created_at, closes_at
                ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
                """,
                (
                    guild_id,
                    channel_id,
                    title,
                    option_a,
                    option_b,
                    created_by,
                    timestamp,
                    closes_at,
                ),
            )
            await connection.commit()
            market_id = int(cursor.lastrowid or 0)
        return await self.get_market(guild_id, market_id)

    async def attach_market_message(
        self, guild_id: int, market_id: int, message_id: int
    ) -> None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                UPDATE markets SET message_id = ?
                WHERE guild_id = ? AND id = ?
                """,
                (message_id, guild_id, market_id),
            )
            if cursor.rowcount == 0:
                await connection.rollback()
                raise MarketNotFound("Mercado não encontrado.")
            await connection.commit()

    async def get_market(self, guild_id: int, market_id: int) -> Market:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM markets WHERE guild_id = ? AND id = ?",
                (guild_id, market_id),
            )
            row = await cursor.fetchone()
        if row is None:
            raise MarketNotFound("Mercado não encontrado neste servidor.")
        return self._market_from_row(row)

    async def get_market_snapshot(self, guild_id: int, market_id: int) -> MarketSnapshot:
        market = await self.get_market(guild_id, market_id)
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN option_key = 'A' THEN amount ELSE 0 END), 0)
                        AS option_a_points,
                    COALESCE(SUM(CASE WHEN option_key = 'B' THEN amount ELSE 0 END), 0)
                        AS option_b_points,
                    COUNT(DISTINCT CASE WHEN option_key = 'A' THEN user_id END)
                        AS option_a_users,
                    COUNT(DISTINCT CASE WHEN option_key = 'B' THEN user_id END)
                        AS option_b_users
                FROM bets
                WHERE market_id = ?
                """,
                (market_id,),
            )
            row = await cursor.fetchone()
        assert row is not None
        return MarketSnapshot(
            market=market,
            option_a_points=int(row["option_a_points"]),
            option_b_points=int(row["option_b_points"]),
            option_a_users=int(row["option_a_users"]),
            option_b_users=int(row["option_b_users"]),
        )

    async def list_open_markets(self, guild_id: int) -> tuple[MarketSnapshot, ...]:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT id FROM markets
                WHERE guild_id = ? AND status = 'OPEN'
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (guild_id,),
            )
            market_ids = [int(row["id"]) for row in await cursor.fetchall()]
        return tuple(
            [await self.get_market_snapshot(guild_id, market_id) for market_id in market_ids]
        )

    async def place_bet(
        self,
        guild_id: int,
        user_id: int,
        market_id: int,
        option: str,
        amount: int,
        *,
        now: int | None = None,
    ) -> BetReceipt:
        timestamp = self._now(now)
        option = option.upper()
        if option not in {"A", "B"}:
            raise InvalidBet("A opção precisa ser A ou B.")
        if amount <= 0:
            raise InvalidBet("O valor precisa ser maior que zero.")

        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status, closes_at FROM markets WHERE guild_id = ? AND id = ?",
                (guild_id, market_id),
            )
            market = await cursor.fetchone()
            if market is None:
                await connection.rollback()
                raise MarketNotFound("Mercado não encontrado neste servidor.")
            if market["status"] != MarketStatus.OPEN:
                await connection.rollback()
                raise MarketUnavailable("Este mercado não está aberto.")
            if market["closes_at"] is not None and int(market["closes_at"]) <= timestamp:
                await connection.rollback()
                raise MarketUnavailable("O prazo deste mercado já terminou.")

            await self._ensure_wallet(connection, guild_id, user_id, timestamp)
            cursor = await connection.execute(
                "SELECT balance FROM wallets WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            wallet = await cursor.fetchone()
            assert wallet is not None
            current_balance = int(wallet["balance"])
            if current_balance < amount:
                await connection.rollback()
                raise InsufficientPoints(
                    f"Saldo insuficiente: você tem {current_balance} pontos."
                )

            try:
                await connection.execute(
                    """
                    INSERT INTO bets (
                        market_id, guild_id, user_id, option_key, amount, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (market_id, guild_id, user_id, option, amount, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                await connection.rollback()
                raise AlreadyBet("Você já apostou neste mercado.") from exc

            new_balance = current_balance - amount
            await connection.execute(
                """
                UPDATE wallets SET balance = ?, updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (new_balance, timestamp, guild_id, user_id),
            )
            await connection.execute(
                """
                INSERT INTO points_ledger (
                    guild_id, user_id, delta, balance_after, reason,
                    reference_type, reference_id, created_at
                ) VALUES (?, ?, ?, ?, 'Aposta realizada', 'market', ?, ?)
                """,
                (guild_id, user_id, -amount, new_balance, market_id, timestamp),
            )
            await connection.commit()

        return BetReceipt(
            market_id=market_id,
            option=option,
            amount=amount,
            new_balance=new_balance,
        )

    async def close_market(
        self, guild_id: int, market_id: int, *, now: int | None = None
    ) -> Market:
        timestamp = self._now(now)
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                UPDATE markets
                SET status = 'CLOSED', closed_at = ?
                WHERE guild_id = ? AND id = ? AND status = 'OPEN'
                """,
                (timestamp, guild_id, market_id),
            )
            if cursor.rowcount == 0:
                check = await connection.execute(
                    "SELECT status FROM markets WHERE guild_id = ? AND id = ?",
                    (guild_id, market_id),
                )
                row = await check.fetchone()
                await connection.rollback()
                if row is None:
                    raise MarketNotFound("Mercado não encontrado neste servidor.")
                raise MarketUnavailable("Este mercado não está aberto.")
            await connection.commit()
        return await self.get_market(guild_id, market_id)

    async def close_expired_markets(self, *, now: int | None = None) -> tuple[tuple[int, int], ...]:
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT guild_id, id
                FROM markets
                WHERE status = 'OPEN' AND closes_at IS NOT NULL AND closes_at <= ?
                """,
                (timestamp,),
            )
            expired = tuple(
                (int(row["guild_id"]), int(row["id"]))
                for row in await cursor.fetchall()
            )
            await connection.execute(
                """
                UPDATE markets SET status = 'CLOSED', closed_at = ?
                WHERE status = 'OPEN' AND closes_at IS NOT NULL AND closes_at <= ?
                """,
                (timestamp, timestamp),
            )
            await connection.commit()
        return expired

    async def settle_market(
        self,
        guild_id: int,
        market_id: int,
        winning_option: str,
        *,
        now: int | None = None,
    ) -> Settlement:
        timestamp = self._now(now)
        winning_option = winning_option.upper()
        if winning_option not in {"A", "B"}:
            raise InvalidBet("A opção vencedora precisa ser A ou B.")

        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status FROM markets WHERE guild_id = ? AND id = ?",
                (guild_id, market_id),
            )
            market = await cursor.fetchone()
            if market is None:
                await connection.rollback()
                raise MarketNotFound("Mercado não encontrado neste servidor.")
            if market["status"] not in {MarketStatus.OPEN, MarketStatus.CLOSED}:
                await connection.rollback()
                raise MarketUnavailable("Este mercado já foi finalizado.")

            cursor = await connection.execute(
                """
                SELECT user_id, option_key, amount
                FROM bets
                WHERE market_id = ?
                ORDER BY id ASC
                """,
                (market_id,),
            )
            bets = list(await cursor.fetchall())
            total_pool = sum(int(bet["amount"]) for bet in bets)
            winning_bets = [bet for bet in bets if bet["option_key"] == winning_option]
            winning_pool = sum(int(bet["amount"]) for bet in winning_bets)
            refunded = bool(bets) and winning_pool == 0

            payout_values: list[tuple[int, int]]
            if refunded:
                payout_values = [
                    (int(bet["user_id"]), int(bet["amount"])) for bet in bets
                ]
            elif winning_pool:
                payout_values = [
                    (
                        int(bet["user_id"]),
                        int(bet["amount"]) * total_pool // winning_pool,
                    )
                    for bet in winning_bets
                ]
                remainder = total_pool - sum(amount for _, amount in payout_values)
                order = sorted(
                    range(len(winning_bets)),
                    key=lambda index: (
                        -int(winning_bets[index]["amount"]),
                        int(winning_bets[index]["user_id"]),
                    ),
                )
                for index in order[:remainder]:
                    user_id, amount = payout_values[index]
                    payout_values[index] = (user_id, amount + 1)
            else:
                payout_values = []

            for user_id, payout in payout_values:
                cursor = await connection.execute(
                    """
                    SELECT balance FROM wallets
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (guild_id, user_id),
                )
                wallet = await cursor.fetchone()
                assert wallet is not None
                balance_after = int(wallet["balance"]) + payout
                await connection.execute(
                    """
                    UPDATE wallets SET balance = ?, updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (balance_after, timestamp, guild_id, user_id),
                )
                await connection.execute(
                    """
                    INSERT INTO points_ledger (
                        guild_id, user_id, delta, balance_after, reason,
                        reference_type, reference_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'market', ?, ?)
                    """,
                    (
                        guild_id,
                        user_id,
                        payout,
                        balance_after,
                        (
                            "Reembolso: nenhuma aposta vencedora"
                            if refunded
                            else "Prêmio de aposta"
                        ),
                        market_id,
                        timestamp,
                    ),
                )

            await connection.execute(
                """
                UPDATE markets
                SET status = 'SETTLED', winning_option = ?, resolved_at = ?,
                    closed_at = COALESCE(closed_at, ?)
                WHERE guild_id = ? AND id = ?
                """,
                (winning_option, timestamp, timestamp, guild_id, market_id),
            )
            await connection.commit()

        return Settlement(
            market_id=market_id,
            winning_option=winning_option,
            total_pool=total_pool,
            winning_pool=winning_pool,
            payouts=tuple(
                UserPayout(user_id=user_id, amount=payout)
                for user_id, payout in payout_values
            ),
            refunded_because_no_winners=refunded,
        )

    async def cancel_market(
        self, guild_id: int, market_id: int, *, now: int | None = None
    ) -> Cancellation:
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT status FROM markets WHERE guild_id = ? AND id = ?",
                (guild_id, market_id),
            )
            market = await cursor.fetchone()
            if market is None:
                await connection.rollback()
                raise MarketNotFound("Mercado não encontrado neste servidor.")
            if market["status"] not in {MarketStatus.OPEN, MarketStatus.CLOSED}:
                await connection.rollback()
                raise MarketUnavailable("Este mercado já foi finalizado.")

            cursor = await connection.execute(
                "SELECT user_id, amount FROM bets WHERE market_id = ? ORDER BY id",
                (market_id,),
            )
            bets = list(await cursor.fetchall())
            for bet in bets:
                user_id = int(bet["user_id"])
                amount = int(bet["amount"])
                wallet_cursor = await connection.execute(
                    "SELECT balance FROM wallets WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                wallet = await wallet_cursor.fetchone()
                assert wallet is not None
                balance_after = int(wallet["balance"]) + amount
                await connection.execute(
                    """
                    UPDATE wallets SET balance = ?, updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (balance_after, timestamp, guild_id, user_id),
                )
                await connection.execute(
                    """
                    INSERT INTO points_ledger (
                        guild_id, user_id, delta, balance_after, reason,
                        reference_type, reference_id, created_at
                    ) VALUES (?, ?, ?, ?, 'Mercado cancelado', 'market', ?, ?)
                    """,
                    (guild_id, user_id, amount, balance_after, market_id, timestamp),
                )

            await connection.execute(
                """
                UPDATE markets
                SET status = 'CANCELLED', resolved_at = ?,
                    closed_at = COALESCE(closed_at, ?)
                WHERE guild_id = ? AND id = ?
                """,
                (timestamp, timestamp, guild_id, market_id),
            )
            await connection.commit()

        return Cancellation(
            market_id=market_id,
            total_refunded=sum(int(bet["amount"]) for bet in bets),
            users_refunded=len(bets),
        )

    async def configure_announcement(
        self,
        guild_id: int,
        channel_id: int,
        message: str,
        interval_seconds: int,
        *,
        now: int | None = None,
    ) -> AnnouncementSetting:
        timestamp = self._now(now)
        message = message.strip()
        if not message:
            raise InvalidBet("A mensagem não pode ficar vazia.")
        if not 30 <= interval_seconds <= 86_400:
            raise InvalidBet("O intervalo precisa ficar entre 30 e 86400 segundos.")
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, announcement_channel_id, announcement_message,
                    announcement_interval_seconds, announcement_enabled,
                    last_announcement_attempt_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    announcement_channel_id = excluded.announcement_channel_id,
                    announcement_message = excluded.announcement_message,
                    announcement_interval_seconds =
                        excluded.announcement_interval_seconds,
                    announcement_enabled = 1,
                    last_announcement_attempt_at =
                        excluded.last_announcement_attempt_at,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id,
                    channel_id,
                    message,
                    interval_seconds,
                    timestamp,
                    timestamp,
                ),
            )
            await connection.commit()
        setting = await self.get_announcement(guild_id)
        assert setting is not None
        return setting

    async def get_announcement(self, guild_id: int) -> AnnouncementSetting | None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            row = await cursor.fetchone()
        return None if row is None else self._announcement_from_row(row)

    async def set_announcement_enabled(
        self, guild_id: int, enabled: bool, *, now: int | None = None
    ) -> AnnouncementSetting:
        timestamp = self._now(now)
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                UPDATE guild_settings
                SET announcement_enabled = ?, last_announcement_attempt_at = ?,
                    updated_at = ?
                WHERE guild_id = ?
                """,
                (int(enabled), timestamp, timestamp, guild_id),
            )
            if cursor.rowcount == 0:
                await connection.rollback()
                raise MarketNotFound("Configure o aviso antes de ativar ou desativar.")
            await connection.commit()
        setting = await self.get_announcement(guild_id)
        assert setting is not None
        return setting

    async def claim_due_announcements(
        self, *, now: int | None = None, limit: int = 100
    ) -> tuple[AnnouncementSetting, ...]:
        timestamp = self._now(now)
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT * FROM guild_settings
                WHERE announcement_enabled = 1
                  AND (
                    last_announcement_attempt_at IS NULL
                    OR last_announcement_attempt_at
                        <= ? - announcement_interval_seconds
                  )
                ORDER BY COALESCE(last_announcement_attempt_at, 0)
                LIMIT ?
                """,
                (timestamp, limit),
            )
            rows = await cursor.fetchall()
            if rows:
                placeholders = ",".join("?" for _ in rows)
                await connection.execute(
                    f"""
                    UPDATE guild_settings
                    SET last_announcement_attempt_at = ?, updated_at = ?
                    WHERE guild_id IN ({placeholders})
                    """,
                    (timestamp, timestamp, *[int(row["guild_id"]) for row in rows]),
                )
            await connection.commit()
        return tuple(self._announcement_from_row(row) for row in rows)

    @staticmethod
    def _market_from_row(row: aiosqlite.Row) -> Market:
        return Market(
            id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            channel_id=int(row["channel_id"]),
            message_id=None if row["message_id"] is None else int(row["message_id"]),
            title=str(row["title"]),
            option_a=str(row["option_a"]),
            option_b=str(row["option_b"]),
            status=MarketStatus(str(row["status"])),
            created_by=int(row["created_by"]),
            created_at=int(row["created_at"]),
            closes_at=None if row["closes_at"] is None else int(row["closes_at"]),
            winning_option=(
                None if row["winning_option"] is None else str(row["winning_option"])
            ),
        )

    @staticmethod
    def _announcement_from_row(row: aiosqlite.Row) -> AnnouncementSetting:
        return AnnouncementSetting(
            guild_id=int(row["guild_id"]),
            channel_id=int(row["announcement_channel_id"]),
            message=str(row["announcement_message"]),
            interval_seconds=int(row["announcement_interval_seconds"]),
            enabled=bool(row["announcement_enabled"]),
        )
