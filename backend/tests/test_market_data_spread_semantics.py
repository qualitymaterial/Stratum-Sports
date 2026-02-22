from datetime import UTC, datetime, timedelta

from app.models.game import Game
from app.models.odds_snapshot import OddsSnapshot
from app.models.user import User
from app.services.market_data import build_dashboard_cards, build_game_detail


def _snapshot(
    *,
    event_id: str,
    home_team: str,
    away_team: str,
    sportsbook_key: str,
    market: str,
    outcome_name: str,
    line: float | None,
    price: int,
    fetched_at: datetime,
    commence_time: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        event_id=event_id,
        sport_key="basketball_nba",
        commence_time=commence_time,
        home_team=home_team,
        away_team=away_team,
        sportsbook_key=sportsbook_key,
        market=market,
        outcome_name=outcome_name,
        line=line,
        price=price,
        fetched_at=fetched_at,
    )


async def test_dashboard_spread_consensus_uses_home_side_only(db_session) -> None:
    now = datetime.now(UTC)
    commence_time = now + timedelta(hours=2)
    event_id = "event_spread_semantics_dash"
    home_team = "Boston Celtics"
    away_team = "New York Knicks"

    db_session.add(
        Game(
            event_id=event_id,
            sport_key="basketball_nba",
            commence_time=commence_time,
            home_team=home_team,
            away_team=away_team,
        )
    )
    user = User(
        email="spread-semantics-dashboard@example.com",
        password_hash="hashed",
        tier="pro",
        is_active=True,
    )
    db_session.add(user)

    fetched_at = now - timedelta(minutes=1)
    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=home_team,
                line=-3.5,
                price=-110,
                fetched_at=fetched_at,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=away_team,
                line=3.5,
                price=-110,
                fetched_at=fetched_at,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=home_team,
                line=-3.0,
                price=-110,
                fetched_at=fetched_at,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=away_team,
                line=3.0,
                price=-110,
                fetched_at=fetched_at,
                commence_time=commence_time,
            ),
        ]
    )
    await db_session.flush()

    cards = await build_dashboard_cards(db_session, user, limit=200)
    assert cards
    card = next(item for item in cards if item["event_id"] == event_id)

    assert card["consensus"]["spreads"] == -3.25
    assert card["consensus"]["spreads"] != 0.0
    assert card["sparkline"][-1] == -3.25


async def test_game_detail_spread_chart_uses_home_side_only(db_session) -> None:
    now = datetime.now(UTC)
    commence_time = now + timedelta(hours=2)
    event_id = "event_spread_semantics_detail"
    home_team = "Los Angeles Lakers"
    away_team = "Boston Celtics"

    db_session.add(
        Game(
            event_id=event_id,
            sport_key="basketball_nba",
            commence_time=commence_time,
            home_team=home_team,
            away_team=away_team,
        )
    )
    user = User(
        email="spread-semantics-detail@example.com",
        password_hash="hashed",
        tier="pro",
        is_active=True,
    )
    db_session.add(user)

    t1 = now - timedelta(minutes=8)
    t2 = now - timedelta(minutes=3)

    db_session.add_all(
        [
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=home_team,
                line=-2.5,
                price=-110,
                fetched_at=t1,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=away_team,
                line=2.5,
                price=-110,
                fetched_at=t1,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=home_team,
                line=-3.0,
                price=-110,
                fetched_at=t1,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=away_team,
                line=3.0,
                price=-110,
                fetched_at=t1,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=home_team,
                line=-4.0,
                price=-110,
                fetched_at=t2,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book1",
                market="spreads",
                outcome_name=away_team,
                line=4.0,
                price=-110,
                fetched_at=t2,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=home_team,
                line=-3.5,
                price=-110,
                fetched_at=t2,
                commence_time=commence_time,
            ),
            _snapshot(
                event_id=event_id,
                home_team=home_team,
                away_team=away_team,
                sportsbook_key="book2",
                market="spreads",
                outcome_name=away_team,
                line=3.5,
                price=-110,
                fetched_at=t2,
                commence_time=commence_time,
            ),
        ]
    )
    await db_session.flush()

    detail = await build_game_detail(db_session, user, event_id)
    assert detail is not None

    spreads = [point["spreads"] for point in detail["chart_series"] if point["spreads"] is not None]
    assert spreads
    assert spreads == [-2.75, -3.75]
