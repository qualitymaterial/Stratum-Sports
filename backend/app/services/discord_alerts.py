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
from app.services.alert_rules import evaluate_signal_for_connection
from app.services.public_signal_surface import is_structural_core_visible, signal_display_type

logger = logging.getLogger(__name__)
settings = get_settings()


def _connection_allows_signal(connection: DiscordConnection, signal: Signal) -> bool:
    allowed, _reason, _thresholds = evaluate_signal_for_connection(
        connection,
        signal,
        steam_discord_enabled=settings.steam_discord_enabled,
    )
    return allowed


def _alert_cooldown_key(user_id: str, signal: Signal) -> str:
    metadata = signal.metadata_json or {}
    outcome = str(metadata.get("outcome_name") or "unknown")
    return (
        f"discord:cooldown:{user_id}:{signal.event_id}:{signal.signal_type}:"
        f"{signal.market}:{outcome.lower()}"
    )


def _format_alert(signal: Signal, game: Game | None) -> str:
    game_line = "Unknown game"
    if game is not None:
        game_line = f"{game.away_team} @ {game.home_team}"
    signal_title = signal_display_type(signal.signal_type)

    if signal.signal_type == "EXCHANGE_DIVERGENCE":
        meta = signal.metadata_json or {}
        divergence_type = str(meta.get("divergence_type", "UNKNOWN"))
        lead_source = str(meta.get("lead_source", "UNKNOWN"))
        lag_seconds = meta.get("lag_seconds")
        exchange_prob = meta.get("exchange_probability")
        lag_display = f"{lag_seconds}s" if lag_seconds is not None else "N/A"
        prob_display = f"{float(exchange_prob):.1%}" if exchange_prob is not None else "N/A"

        return (
            "**STRATUM SIGNAL - NBA**\n"
            "Title: EXCHANGE DIVERGENCE\n"
            f"Game: {game_line}\n"
            f"Divergence: {divergence_type}\n"
            f"Lead: {lead_source}\n"
            f"Lag: {lag_display}\n"
            f"Exchange Prob: {prob_display}\n"
            f"Strength: {signal.strength_score}"
        )

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
        f"Title: {signal_title}\n"
        f"Game: {game_line}\n"
        f"Market: {market_label}\n"
        f"Move: {move}\n"
        f"Velocity: {round(signal.velocity_minutes, 2)} minutes\n"
        f"Books: {signal.books_affected}\n"
        f"Strength: {signal.strength_score}"
    )


async def dispatch_discord_alerts_for_signals(
    db: AsyncSession,
    signals: list[Signal],
    redis=None,
) -> dict[str, int]:
    if not signals:
        return {"sent": 0, "failed": 0}

    signals = [
        signal
        for signal in signals
        if is_structural_core_visible(
            signal_type=signal.signal_type,
            market=signal.market,
            strength_score=signal.strength_score,
            min_samples=None,
            context="dispatch_discord_alerts_for_signals",
        )
    ]
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
            user_id = str(watchlist_item.user_id)
            for signal in signals:
                if signal.event_id != watchlist_item.event_id:
                    continue

                cooldown_active = False
                thresholds_cooldown_seconds = 0
                if redis is not None:
                    _allowed, _reason, thresholds = evaluate_signal_for_connection(
                        connection,
                        signal,
                        steam_discord_enabled=settings.steam_discord_enabled,
                    )
                    thresholds_cooldown_seconds = max(0, thresholds.cooldown_minutes) * 60
                    if thresholds_cooldown_seconds > 0:
                        key = _alert_cooldown_key(user_id, signal)
                        try:
                            cooldown_active = bool(await redis.get(key))
                        except Exception:
                            logger.exception("Discord cooldown redis read failed")

                allowed, reason, thresholds = evaluate_signal_for_connection(
                    connection,
                    signal,
                    steam_discord_enabled=settings.steam_discord_enabled,
                    cooldown_active=cooldown_active,
                )
                if not allowed:
                    logger.debug(
                        "Skipping Discord alert",
                        extra={
                            "user_id": user_id,
                            "event_id": signal.event_id,
                            "signal_type": signal.signal_type,
                            "reason": reason,
                        },
                    )
                    continue

                payload = {"content": _format_alert(signal, games.get(signal.event_id))}
                try:
                    response = await client.post(connection.webhook_url, json=payload)
                    response.raise_for_status()
                    sent += 1
                    cooldown_seconds = thresholds_cooldown_seconds or (max(0, thresholds.cooldown_minutes) * 60)
                    if redis is not None and cooldown_seconds > 0:
                        try:
                            await redis.set(_alert_cooldown_key(user_id, signal), "1", ex=cooldown_seconds)
                        except Exception:
                            logger.exception("Discord cooldown redis write failed")
                except Exception:
                    failed += 1
                    logger.exception(
                        "Failed to send Discord webhook",
                        extra={"user_id": str(watchlist_item.user_id), "event_id": signal.event_id},
                    )

    if sent:
        logger.info("Discord alerts sent", extra={"count": sent})

    return {"sent": sent, "failed": failed}
