import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class OddsFetchResult:
    events: list[dict]
    requests_remaining: int | None = None
    requests_used: int | None = None
    requests_last: int | None = None
    requests_limit: int | None = None
    history_timestamp: datetime | None = None
    previous_timestamp: datetime | None = None
    next_timestamp: datetime | None = None


@dataclass
class HistoryProbeResult:
    endpoint_variant: Literal["bulk", "event"]
    status_code: int
    body_preview: str
    events_found: int
    requests_remaining: int | None = None
    requests_last: int | None = None
    requests_limit: int | None = None


def _parse_header_int(headers: httpx.Headers, key: str) -> int | None:
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _to_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed_value = value.strip()
    if not parsed_value:
        return None
    if parsed_value.endswith("Z"):
        parsed_value = parsed_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(parsed_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_history_events(payload: object) -> tuple[list[dict], datetime | None, datetime | None, datetime | None]:
    events: list[dict] = []
    history_timestamp: datetime | None = None
    previous_timestamp: datetime | None = None
    next_timestamp: datetime | None = None

    if isinstance(payload, list):
        events = [event for event in payload if isinstance(event, dict)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            events = [event for event in payload["data"] if isinstance(event, dict)]
        elif isinstance(payload.get("events"), list):
            events = [event for event in payload["events"] if isinstance(event, dict)]
        elif payload.get("id") and isinstance(payload.get("bookmakers"), list):
            events = [payload]

        history_timestamp = _parse_iso_datetime(payload.get("timestamp")) or _parse_iso_datetime(payload.get("date"))
        previous_timestamp = _parse_iso_datetime(payload.get("previous_timestamp"))
        next_timestamp = _parse_iso_datetime(payload.get("next_timestamp"))
    else:
        logger.warning("Unexpected history payload type", extra={"type": str(type(payload))})

    return events, history_timestamp, previous_timestamp, next_timestamp


class OddsApiClient:
    async def fetch_nba_odds(
        self,
        *,
        sport_key: str = "basketball_nba",
        markets: str | None = None,
        regions: str | None = None,
        bookmakers: str | None = None,
    ) -> OddsFetchResult:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping polling cycle")
            return OddsFetchResult(events=[])

        url = f"{settings.odds_api_base_url}/sports/{sport_key}/odds"
        params = {
            "apiKey": settings.odds_api_key,
            "regions": regions if regions is not None else settings.odds_api_regions,
            "markets": markets if markets is not None else settings.odds_api_markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        configured_books = bookmakers if bookmakers is not None else settings.odds_api_bookmakers
        if configured_books.strip():
            params["bookmakers"] = configured_books

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            fetch_result = OddsFetchResult(
                events=payload if isinstance(payload, list) else [],
                requests_remaining=_parse_header_int(response.headers, "x-requests-remaining"),
                requests_used=_parse_header_int(response.headers, "x-requests-used"),
                requests_last=_parse_header_int(response.headers, "x-requests-last"),
                requests_limit=_parse_header_int(response.headers, "x-requests-limit"),
            )

        if not isinstance(payload, list):
            logger.warning("Unexpected odds payload type", extra={"type": str(type(payload))})
            return fetch_result

        if fetch_result.requests_remaining is not None:
            logger.info(
                "Odds API response received",
                extra={
                    "events_seen": len(fetch_result.events),
                    "requests_remaining": fetch_result.requests_remaining,
                    "requests_used": fetch_result.requests_used,
                    "requests_last": fetch_result.requests_last,
                    "requests_limit": fetch_result.requests_limit,
                },
            )

        return fetch_result

    def _history_url(
        self,
        *,
        sport_key: str,
        endpoint_variant: Literal["bulk", "event"],
        event_id: str | None = None,
    ) -> str:
        if endpoint_variant == "bulk":
            return f"{settings.odds_api_base_url}/historical/sports/{sport_key}/odds"
        if not event_id:
            raise ValueError("event_id is required for event history endpoint")
        return f"{settings.odds_api_base_url}/historical/sports/{sport_key}/events/{event_id}/odds"

    def _history_params(
        self,
        *,
        markets: str | None,
        regions: str | None,
        bookmakers: str | None,
        date: datetime,
    ) -> dict[str, str]:
        params: dict[str, str] = {
            "apiKey": settings.odds_api_key,
            "regions": regions if regions is not None else settings.odds_api_regions,
            "markets": markets if markets is not None else settings.odds_api_markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
            "date": _to_iso_z(date),
        }

        configured_books = bookmakers if bookmakers is not None else settings.odds_api_bookmakers
        if configured_books.strip():
            params["bookmakers"] = configured_books
        return params

    async def probe_nba_odds_history(
        self,
        *,
        sport_key: str = "basketball_nba",
        endpoint_variant: Literal["bulk", "event"] = "bulk",
        event_id: str | None = None,
        markets: str | None = None,
        regions: str | None = None,
        bookmakers: str | None = None,
        date: datetime,
    ) -> HistoryProbeResult:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping history probe")
            return HistoryProbeResult(
                endpoint_variant=endpoint_variant,
                status_code=0,
                body_preview="",
                events_found=0,
            )

        url = self._history_url(
            sport_key=sport_key,
            endpoint_variant=endpoint_variant,
            event_id=event_id,
        )
        params = self._history_params(
            markets=markets,
            regions=regions,
            bookmakers=bookmakers,
            date=date,
        )

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)

        body_preview = response.text[:200]
        events_found = 0
        try:
            payload = response.json()
            events, _history_timestamp, _previous_timestamp, _next_timestamp = _extract_history_events(payload)
            events_found = len(events)
        except Exception:
            events_found = 0

        return HistoryProbeResult(
            endpoint_variant=endpoint_variant,
            status_code=response.status_code,
            body_preview=body_preview,
            events_found=events_found,
            requests_remaining=_parse_header_int(response.headers, "x-requests-remaining"),
            requests_last=_parse_header_int(response.headers, "x-requests-last"),
            requests_limit=_parse_header_int(response.headers, "x-requests-limit"),
        )

    async def fetch_nba_odds_history(
        self,
        *,
        sport_key: str = "basketball_nba",
        endpoint_variant: Literal["bulk", "event"] = "bulk",
        event_id: str | None = None,
        markets: str | None = None,
        regions: str | None = None,
        bookmakers: str | None = None,
        date: datetime,
    ) -> OddsFetchResult:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping history fetch")
            return OddsFetchResult(events=[])

        url = self._history_url(
            sport_key=sport_key,
            endpoint_variant=endpoint_variant,
            event_id=event_id,
        )
        params = self._history_params(
            markets=markets,
            regions=regions,
            bookmakers=bookmakers,
            date=date,
        )

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        events, history_timestamp, previous_timestamp, next_timestamp = _extract_history_events(payload)
        if history_timestamp is None:
            history_timestamp = date.astimezone(UTC)

        fetch_result = OddsFetchResult(
            events=events,
            requests_remaining=_parse_header_int(response.headers, "x-requests-remaining"),
            requests_used=_parse_header_int(response.headers, "x-requests-used"),
            requests_last=_parse_header_int(response.headers, "x-requests-last"),
            requests_limit=_parse_header_int(response.headers, "x-requests-limit"),
            history_timestamp=history_timestamp,
            previous_timestamp=previous_timestamp,
            next_timestamp=next_timestamp,
        )

        logger.info(
            "Odds API history response received",
            extra={
                "sport_key": sport_key,
                "endpoint_variant": endpoint_variant,
                "event_id": event_id,
                "events_seen": len(fetch_result.events),
                "requests_remaining": fetch_result.requests_remaining,
                "requests_last": fetch_result.requests_last,
                "requests_limit": fetch_result.requests_limit,
            },
        )
        return fetch_result
