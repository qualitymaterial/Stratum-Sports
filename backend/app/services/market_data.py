from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tier import delayed_cutoff_for_user, is_pro
from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.signal import Signal
from app.models.user import User
from app.services.context_score import build_context_score
from app.services.performance_intel import build_liquidity_heatmap
from app.services.public_signal_surface import is_structural_core_visible
from app.services.signals import serialize_signal


def _avg(values: list[float]) -> float | None:
    return float(mean(values)) if values else None


async def list_upcoming_games(
    db: AsyncSession,
    *,
    limit: int = 25,
    sport_key: str | None = None,
) -> list[Game]:
    # Include games that started up to 6 hours ago (still in-play for NBA)
    now = datetime.now(UTC) - timedelta(hours=6)
    filters = [Game.commence_time >= now]
    if sport_key:
        filters.append(Game.sport_key == sport_key)

    stmt = select(Game).where(and_(*filters)).order_by(Game.commence_time.asc()).limit(limit)
    return (await db.execute(stmt)).scalars().all()


async def build_dashboard_cards(
    db: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    sport_key: str | None = None,
) -> list[dict]:
    pro_user = is_pro(user)
    games = await list_upcoming_games(db, limit=limit, sport_key=sport_key)
    if not games:
        return []

    event_ids = [game.event_id for game in games]
    cutoff = delayed_cutoff_for_user(user)

    snapshot_filters = [OddsSnapshot.event_id.in_(event_ids)]
    if cutoff:
        snapshot_filters.append(OddsSnapshot.fetched_at <= cutoff)

    snapshots_stmt = (
        select(OddsSnapshot)
        .where(and_(*snapshot_filters))
        .order_by(OddsSnapshot.fetched_at.asc())
    )
    snapshots = (await db.execute(snapshots_stmt)).scalars().all()

    signal_stmt = (
        select(Signal)
        .where(Signal.event_id.in_(event_ids))
        .order_by(desc(Signal.created_at))
        .limit(200)
    )
    signals = (await db.execute(signal_stmt)).scalars().all()
    signals = [
        signal
        for signal in signals
        if is_structural_core_visible(
            signal_type=signal.signal_type,
            market=signal.market,
            strength_score=signal.strength_score,
            min_samples=None,
            context="build_dashboard_cards",
        )
    ]

    snapshots_by_event: dict[str, list[OddsSnapshot]] = defaultdict(list)
    for snap in snapshots:
        snapshots_by_event[snap.event_id].append(snap)

    signals_by_event: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        if len(signals_by_event[signal.event_id]) >= 4:
            continue
        signals_by_event[signal.event_id].append(signal)

    cards: list[dict] = []
    for game in games:
        event_snaps = snapshots_by_event.get(game.event_id, [])
        latest_keyed: dict[tuple[str, str, str], OddsSnapshot] = {}
        sparkline_map: dict[datetime, list[float]] = defaultdict(list)

        for snap in event_snaps:
            latest_keyed[(snap.sportsbook_key, snap.market, snap.outcome_name)] = snap
            if (
                snap.market == "spreads"
                and snap.line is not None
                and snap.outcome_name == game.home_team
            ):
                sparkline_map[snap.fetched_at].append(snap.line)

        spreads = [
            snap.line
            for snap in latest_keyed.values()
            if (
                snap.market == "spreads"
                and snap.line is not None
                and snap.outcome_name == game.home_team
            )
        ]
        totals = [
            snap.line
            for snap in latest_keyed.values()
            if snap.market == "totals" and snap.line is not None
        ]
        h2h_home = [
            float(snap.price)
            for snap in latest_keyed.values()
            if snap.market == "h2h" and snap.outcome_name == game.home_team
        ]
        h2h_away = [
            float(snap.price)
            for snap in latest_keyed.values()
            if snap.market == "h2h" and snap.outcome_name == game.away_team
        ]

        sparkline = [
            round(_avg(v) or 0.0, 3)
            for _, v in sorted(sparkline_map.items(), key=lambda i: i[0])[-24:]
        ]

        cards.append(
            {
                "event_id": game.event_id,
                "sport_key": game.sport_key,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "commence_time": game.commence_time,
                "consensus": {
                    "spreads": _avg([v for v in spreads if v is not None]),
                    "totals": _avg([v for v in totals if v is not None]),
                    "h2h_home": int(round(_avg(h2h_home))) if h2h_home else None,
                    "h2h_away": int(round(_avg(h2h_away))) if h2h_away else None,
                },
                "sparkline": sparkline,
                "signals": [
                    serialize_signal(signal, pro_user=pro_user)
                    for signal in signals_by_event.get(game.event_id, [])
                ],
            }
        )

    return cards


async def build_game_detail(db: AsyncSession, user: User, event_id: str) -> dict | None:
    pro_user = is_pro(user)
    game_stmt = select(Game).where(Game.event_id == event_id)
    game = (await db.execute(game_stmt)).scalar_one_or_none()
    if game is None:
        return None

    cutoff = delayed_cutoff_for_user(user)
    snapshot_filters = [OddsSnapshot.event_id == event_id]
    if cutoff:
        snapshot_filters.append(OddsSnapshot.fetched_at <= cutoff)

    snapshots_stmt = (
        select(OddsSnapshot)
        .where(and_(*snapshot_filters))
        .order_by(OddsSnapshot.fetched_at.asc())
    )
    snapshots = (await db.execute(snapshots_stmt)).scalars().all()

    latest_keyed: dict[tuple[str, str, str], OddsSnapshot] = {}
    chart_bucket: dict[datetime, dict[str, list[float]]] = defaultdict(
        lambda: {"spreads": [], "totals": [], "h2h_home": [], "h2h_away": []}
    )

    for snap in snapshots:
        latest_keyed[(snap.sportsbook_key, snap.market, snap.outcome_name)] = snap
        point = chart_bucket[snap.fetched_at]
        if (
            snap.market == "spreads"
            and snap.line is not None
            and snap.outcome_name == game.home_team
        ):
            point["spreads"].append(snap.line)
        if snap.market == "totals" and snap.line is not None:
            point["totals"].append(snap.line)
        if snap.market == "h2h" and snap.outcome_name == game.home_team:
            point["h2h_home"].append(float(snap.price))
        if snap.market == "h2h" and snap.outcome_name == game.away_team:
            point["h2h_away"].append(float(snap.price))

    odds_rows = [
        {
            "sportsbook_key": snap.sportsbook_key,
            "market": snap.market,
            "outcome_name": snap.outcome_name,
            "line": snap.line,
            "price": snap.price,
            "fetched_at": snap.fetched_at,
        }
        for snap in sorted(
            latest_keyed.values(),
            key=lambda s: (s.sportsbook_key, s.market, s.outcome_name),
        )
    ]

    chart_series = [
        {
            "timestamp": ts,
            "spreads": _avg(values["spreads"]),
            "totals": _avg(values["totals"]),
            "h2h_home": _avg(values["h2h_home"]),
            "h2h_away": _avg(values["h2h_away"]),
        }
        for ts, values in sorted(chart_bucket.items(), key=lambda i: i[0])[-120:]
    ]

    signal_stmt = (
        select(Signal)
        .where(Signal.event_id == event_id)
        .order_by(desc(Signal.created_at))
        .limit(200 if pro_user else 40)
    )
    signals = (await db.execute(signal_stmt)).scalars().all()
    signals = [
        signal
        for signal in signals
        if is_structural_core_visible(
            signal_type=signal.signal_type,
            market=signal.market,
            strength_score=signal.strength_score,
            min_samples=None,
            context="build_game_detail",
        )
    ]

    return {
        "event_id": game.event_id,
        "home_team": game.home_team,
        "away_team": game.away_team,
        "commence_time": game.commence_time,
        "odds": odds_rows,
        "chart_series": chart_series,
        "signals": [serialize_signal(signal, pro_user=pro_user) for signal in signals],
        "context_scaffold": await build_context_score(db, event_id),
        "liquidity_heatmap": build_liquidity_heatmap(game),
    }
