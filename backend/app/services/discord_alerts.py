import logging

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.discord_connection import DiscordConnection
from app.models.game import Game
from app.models.signal import Signal
from app.models.user import User
from app.models.watchlist import Watchlist

logger = logging.getLogger(__name__)
settings = get_settings()


def _connection_allows_signal(connection: DiscordConnection, signal: Signal) -> bool:
    if not connection.is_enabled:
        return False
    if signal.strength_score < connection.min_strength:
        return False

    if signal.signal_type == "STEAM":
        if not settings.steam_discord_enabled:
            return False
        if signal.market == "spreads":
            return connection.alert_spreads
        if signal.market == "totals":
            return connection.alert_totals
        return False

    if signal.signal_type == "DISLOCATION":
        if signal.market == "spreads":
            return connection.alert_spreads
        if signal.market == "totals":
            return connection.alert_totals
        return connection.alert_multibook

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

    if signal.signal_type == "DISLOCATION":
        meta = signal.metadata_json or {}
        market_label = signal.market.replace("h2h", "Moneyline").title()
        outcome_name = str(meta.get("outcome_name", "Unknown"))
        book_key = str(meta.get("book_key", "N/A")).upper()
        delta = meta.get("delta")
        delta_display = "N/A"
        if isinstance(delta, (float, int)):
            delta_display = f"{float(delta):+.4f}" if meta.get("delta_type") == "implied_prob" else f"{float(delta):+.2f}"

        book_line = meta.get("book_line")
        consensus_line = meta.get("consensus_line")
        book_price = meta.get("book_price")
        consensus_price = meta.get("consensus_price")
        dispersion = meta.get("dispersion")
        books_count = meta.get("books_count")

        if signal.market == "h2h":
            comparison = f"{book_key}: {book_price} vs CONS: {consensus_price} (Δ {delta_display})"
        else:
            comparison = f"{book_key}: {book_line} vs CONS: {consensus_line} (Δ {delta_display})"

        return (
            "**STRATUM SIGNAL - NBA**\n"
            "Title: DISLOCATION\n"
            f"Game: {game_line}\n"
            f"Market: {market_label}\n"
            f"Outcome: {outcome_name}\n"
            f"Book vs Consensus: {comparison}\n"
            f"Books: {books_count}\n"
            f"Dispersion: {dispersion}\n"
            f"Strength: {signal.strength_score}"
        )

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


async def dispatch_discord_alerts_for_signals(db: AsyncSession, signals: list[Signal]) -> dict[str, int]:
    if not signals:
        return {"sent": 0, "failed": 0}

    event_ids = {signal.event_id for signal in signals}
    if not event_ids:
        return {"sent": 0, "failed": 0}

    watchers_stmt = (
        select(Watchlist, User, DiscordConnection)
        .join(User, User.id == Watchlist.user_id)
        .join(DiscordConnection, DiscordConnection.user_id == User.id)
        .where(
            Watchlist.event_id.in_(event_ids),
            or_(User.tier == "pro", User.is_admin.is_(True)),
        )
    )
    watcher_rows = (await db.execute(watchers_stmt)).all()

    if not watcher_rows:
        return {"sent": 0, "failed": 0}

    games_stmt = select(Game).where(Game.event_id.in_(event_ids))
    games = {game.event_id: game for game in (await db.execute(games_stmt)).scalars().all()}

    sent = 0
    failed = 0
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
                    failed += 1
                    logger.exception(
                        "Failed to send Discord webhook",
                        extra={"user_id": str(watchlist_item.user_id), "event_id": signal.event_id},
                    )

    if sent:
        logger.info("Discord alerts sent", extra={"count": sent})

    return {"sent": sent, "failed": failed}
