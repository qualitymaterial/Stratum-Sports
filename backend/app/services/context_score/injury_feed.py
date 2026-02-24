"""Optional live injury-feed integration for context scoring.

This module is intentionally defensive:
- If provider config is missing/invalid, returns None.
- If provider requests fail, returns None.
- The caller (injuries.py) must fall back to heuristic scoring.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.models.game import Game

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


_SPORT_ENDPOINT_ATTR: dict[str, str] = {
    "basketball_nba": "sportsdataio_injuries_endpoint_nba",
    "basketball_ncaab": "sportsdataio_injuries_endpoint_ncaab",
    "americanfootball_nfl": "sportsdataio_injuries_endpoint_nfl",
}


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _team_aliases(team_name: str | None) -> set[str]:
    normalized = _normalize(team_name)
    if not normalized:
        return set()
    parts = normalized.split()
    aliases = {normalized}
    if parts:
        aliases.add(parts[-1])
    if len(parts) >= 2:
        aliases.add(" ".join(parts[-2:]))
    return aliases


def _resolve_endpoint(sport_key: str) -> str:
    attr = _SPORT_ENDPOINT_ATTR.get(sport_key)
    if not attr:
        return ""
    return str(getattr(settings, attr, "")).strip()


def _expand_templated_endpoint(sport_key: str, endpoint: str) -> str | None:
    expanded = endpoint.strip()
    if not expanded:
        return None
    if "{team}" in expanded:
        logger.warning(
            "SportsDataIO injury endpoint with {team} template is not supported by current fetcher",
            extra={"sport_key": sport_key},
        )
        return None

    if sport_key == "americanfootball_nfl":
        season = settings.sportsdataio_nfl_injuries_season.strip()
        week = settings.sportsdataio_nfl_injuries_week.strip()
        if "{season}" in expanded:
            if not season:
                logger.info(
                    "SPORTSDATAIO_NFL_INJURIES_SEASON missing; skipping NFL injury feed",
                    extra={"sport_key": sport_key},
                )
                return None
            expanded = expanded.replace("{season}", season)
        if "{week}" in expanded:
            if not week:
                logger.info(
                    "SPORTSDATAIO_NFL_INJURIES_WEEK missing; skipping NFL injury feed",
                    extra={"sport_key": sport_key},
                )
                return None
            expanded = expanded.replace("{week}", week)

    if re.search(r"\{[^{}]+\}", expanded):
        logger.warning(
            "SportsDataIO injury endpoint still contains unresolved template placeholders",
            extra={"sport_key": sport_key, "endpoint": expanded},
        )
        return None
    return expanded


def _build_url(endpoint: str) -> str:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    base = settings.sportsdataio_base_url.rstrip("/") + "/"
    return urljoin(base, endpoint.lstrip("/"))


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [row for row in payload["data"] if isinstance(row, dict)]
        if isinstance(payload.get("players"), list):
            return [row for row in payload["players"] if isinstance(row, dict)]
    return []


def _extract_status(row: dict[str, Any]) -> str:
    for key in (
        "InjuryStatus",
        "InjuryDesignation",
        "Injury",
        "StatusDescription",
        "Status",
    ):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _status_weight(status: str) -> float:
    value = _normalize(status)
    if not value:
        return 0.0
    if "out" in value or "injured reserve" in value or value == "injured" or value == "ir":
        return 1.0
    if "doubtful" in value:
        return 0.8
    if "questionable" in value:
        return 0.6
    if "day to day" in value:
        return 0.5
    if "probable" in value:
        return 0.25
    if "inactive" in value or "suspended" in value:
        return 0.4
    return 0.15


def _match_game_team(raw_team: str, home_aliases: set[str], away_aliases: set[str]) -> str | None:
    team = _normalize(raw_team)
    if not team:
        return None
    if team in home_aliases or any(alias and alias in team for alias in home_aliases):
        return "home"
    if team in away_aliases or any(alias and alias in team for alias in away_aliases):
        return "away"
    return None


async def _fetch_rows(sport_key: str) -> list[dict[str, Any]]:
    configured_endpoint = _resolve_endpoint(sport_key)
    endpoint = _expand_templated_endpoint(sport_key, configured_endpoint)
    if not endpoint or not settings.sportsdataio_api_key:
        return []

    cache_key = f"{sport_key}:{endpoint}"
    now = datetime.now(UTC)
    ttl_seconds = max(30, settings.sportsdataio_cache_seconds)
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    url = _build_url(endpoint)
    headers = {
        "Ocp-Apim-Subscription-Key": settings.sportsdataio_api_key,
        "X-Api-Key": settings.sportsdataio_api_key,
    }

    timeout = max(2.0, settings.sportsdataio_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params={"key": settings.sportsdataio_api_key}, headers=headers)
        response.raise_for_status()
        payload = response.json()

    rows = _extract_rows(payload)
    _CACHE[cache_key] = (now + timedelta(seconds=ttl_seconds), rows)
    return rows


async def get_sportsdataio_injury_context(game: Game) -> dict[str, Any] | None:
    if settings.injury_feed_provider.strip().lower() != "sportsdataio":
        return None
    if not settings.sportsdataio_api_key:
        return None

    endpoint = _resolve_endpoint(game.sport_key)
    if not endpoint:
        logger.info(
            "SportsDataIO endpoint missing for sport; skipping live injury feed",
            extra={"sport_key": game.sport_key},
        )
        return None

    try:
        rows = await _fetch_rows(game.sport_key)
    except Exception:  # noqa: BLE001
        logger.warning(
            "SportsDataIO injury request failed; falling back to heuristic injury context",
            exc_info=True,
            extra={"sport_key": game.sport_key, "event_id": game.event_id},
        )
        return None

    if not rows:
        return None

    home_aliases = _team_aliases(game.home_team)
    away_aliases = _team_aliases(game.away_team)
    home_flagged = 0
    away_flagged = 0
    weighted_total = 0.0
    impacted_rows = 0
    strong_status_count = 0

    for row in rows:
        team_raw = str(
            row.get("Team")
            or row.get("TeamName")
            or row.get("TeamKey")
            or row.get("TeamAbbreviation")
            or ""
        )
        side = _match_game_team(team_raw, home_aliases, away_aliases)
        if side is None:
            continue

        status = _extract_status(row)
        weight = _status_weight(status)
        if weight <= 0:
            continue

        impacted_rows += 1
        weighted_total += weight
        normalized_status = _normalize(status)
        if any(flag in normalized_status for flag in ("out", "injured", "reserve", "doubtful")):
            strong_status_count += 1
        if side == "home":
            home_flagged += 1
        else:
            away_flagged += 1

    if impacted_rows == 0:
        return None

    score = int(
        min(
            100,
            round(weighted_total * 15 + strong_status_count * 4 + min(home_flagged + away_flagged, 8) * 2),
        )
    )

    return {
        "event_id": game.event_id,
        "component": "injuries",
        "status": "computed",
        "score": score,
        "details": {
            "source": "sportsdataio",
            "players_flagged": impacted_rows,
            "home_players_flagged": home_flagged,
            "away_players_flagged": away_flagged,
            "weighted_injury_load": round(weighted_total, 2),
        },
        "notes": "Derived from SportsDataIO injury statuses for teams in this matchup.",
    }
