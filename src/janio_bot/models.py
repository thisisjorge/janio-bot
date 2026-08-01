from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MarketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Market:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    title: str
    option_a: str
    option_b: str
    status: MarketStatus
    created_by: int
    created_at: int
    closes_at: int | None
    winning_option: str | None


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    market: Market
    option_a_points: int
    option_b_points: int
    option_a_users: int
    option_b_users: int

    @property
    def total_points(self) -> int:
        return self.option_a_points + self.option_b_points


@dataclass(frozen=True, slots=True)
class BetReceipt:
    market_id: int
    option: str
    amount: int
    new_balance: int


@dataclass(frozen=True, slots=True)
class UserPayout:
    user_id: int
    amount: int


@dataclass(frozen=True, slots=True)
class Settlement:
    market_id: int
    winning_option: str
    total_pool: int
    winning_pool: int
    payouts: tuple[UserPayout, ...]
    refunded_because_no_winners: bool


@dataclass(frozen=True, slots=True)
class Cancellation:
    market_id: int
    total_refunded: int
    users_refunded: int


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    user_id: int
    balance: int


@dataclass(frozen=True, slots=True)
class AnnouncementSetting:
    guild_id: int
    channel_id: int
    message: str
    interval_seconds: int
    enabled: bool
