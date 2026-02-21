from datetime import datetime

from pydantic import BaseModel

from app.schemas.signal import SignalOut


class ConsensusSnapshot(BaseModel):
    spreads: float | None = None
    totals: float | None = None
    h2h_home: int | None = None
    h2h_away: int | None = None


class DashboardCard(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    consensus: ConsensusSnapshot
    sparkline: list[float]
    signals: list[SignalOut]


class OddsRow(BaseModel):
    sportsbook_key: str
    market: str
    outcome_name: str
    line: float | None
    price: int
    fetched_at: datetime


class GameDetailOut(BaseModel):
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    odds: list[OddsRow]
    chart_series: list[dict]
    signals: list[SignalOut]
    context_scaffold: dict | None = None
