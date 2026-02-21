import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.signal import Signal
from app.models.user import User
from app.models.watchlist import Watchlist

logger = logging.getLogger(__name__)


def _connection_allows_signal(connection: DiscordConnection, signal: Signal) -> bool:
    if not connection.is_enabled:
        return False
    if signal.strength_score < connection.min_strength:
        return False

    if signal.signal_type == "MULTIBOOK_SYNC":
        return connection.alert_multibook
    if signal.market == "spreads":
        return connection.alert_spreads
    if signal.market == "totals":
        return connection.alert_totals
    return False


def _format_alert(signal: Signal, game: Game | None) -> str:
    game_line = "Unknown game"
    if game is not None:
        game_line = f"{game.away_team} @ {game.home_team}"

    market_label = signal.market.replace("h2h", "Moneyline").title()
    move = f"{signal.from_value} -> {signal.to_value}"

    return (
        "**STRATUM SIGNAL - NBA**\n"
        f"Game: {game_line}\n"
        f"Market: {market_label}\n"
        f"Move: {move}\n"
        f"Velocity: {round(signal.velocity_minutes, 2)} minutes\n"
        f"Books: {signal.books_affected}\n"
        f"Strength: {signal.strength_score}"
    )


async def dispatch_discord_alerts_for_signals(db: AsyncSession, signals: list[Signal]) -> int:
    if not signals:
        return 0

    event_ids = {signal.event_id for signal in signals}
    if not event_ids:
        return 0

    watchers_stmt = (
        select(Watchlist, User, DiscordConnection)
        .join(User, User.id == Watchlist.user_id)
        .join(DiscordConnection, DiscordConnection.user_id == User.id)
        .where(Watchlist.event_id.in_(event_ids), User.tier == "pro")
    )
    watcher_rows = (await db.execute(watchers_stmt)).all()

    if not watcher_rows:
        return 0

    games_stmt = select(Game).where(Game.event_id.in_(event_ids))
    games = {game.event_id: game for game in (await db.execute(games_stmt)).scalars().all()}

    sent = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for watchlist_item, _user, connection in watcher_rows:
            for signal in signals:
                if signal.event_id != watchlist_item.event_id:
                    continue
                if not _connection_allows_signal(connection, signal):
                    continue

                payload = {"content": _format_alert(signal, games.get(signal.event_id))}
                try:
                    response = await client.post(connection.webhook_url, json=payload)
                    response.raise_for_status()
                    sent += 1
                except Exception:
                    logger.exception(
                        "Failed to send Discord webhook",
                        extra={"user_id": str(watchlist_item.user_id), "event_id": signal.event_id},
                    )

    if sent:
        logger.info("Discord alerts sent", extra={"count": sent})

    return sent
