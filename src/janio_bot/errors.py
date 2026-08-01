from __future__ import annotations


class JanioError(Exception):
    """Base class for expected, user-facing errors."""


class MarketNotFound(JanioError):
    pass


class MarketUnavailable(JanioError):
    pass


class InvalidBet(JanioError):
    pass


class AlreadyBet(JanioError):
    pass


class InsufficientPoints(JanioError):
    pass


class DailyAlreadyClaimed(JanioError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("O resgate diário ainda não está disponível.")
        self.retry_after_seconds = retry_after_seconds


class ExternalServiceError(JanioError):
    pass


class ChampionNotFound(JanioError):
    pass


class RiotApiNotConfigured(JanioError):
    pass
