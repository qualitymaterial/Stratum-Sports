import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    _consecutive_failures: int = 0
    _circuit_open_until: datetime | None = None

    @classmethod
    def _is_circuit_open(cls, now: datetime) -> bool:
        if cls._circuit_open_until is None:
            return False
        if now >= cls._circuit_open_until:
            cls._circuit_open_until = None
            cls._consecutive_failures = 0
            return False
        return True

    @classmethod
    def _record_success(cls) -> None:
        cls._consecutive_failures = 0
        cls._circuit_open_until = None

    @classmethod
    def _record_failure(cls) -> None:
        cls._consecutive_failures += 1
        failures_to_open = max(1, settings.odds_api_circuit_failures_to_open)
        if cls._consecutive_failures < failures_to_open:
            return
        open_seconds = max(5, settings.odds_api_circuit_open_seconds)
        cls._circuit_open_until = datetime.now(UTC) + timedelta(seconds=open_seconds)
        logger.warning(
            "Odds API circuit opened",
            extra={
                "circuit_open_seconds": open_seconds,
                "consecutive_failures": cls._consecutive_failures,
            },
        )

    async def fetch_nba_odds(
        self,
        *,
        sport_key: str = "basketball_nba",
        markets: str | None = None,
        regions: str | None = None,
        bookmakers: str | None = None,
        event_ids: str | None = None,
    ) -> OddsFetchResult:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping polling cycle")
            return OddsFetchResult(events=[])

        now = datetime.now(UTC)
        if self._is_circuit_open(now):
            logger.warning(
                "Odds API circuit is open; skipping fetch",
                extra={
                    "circuit_open_until": self._circuit_open_until.isoformat()
                    if self._circuit_open_until is not None
                    else None,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
            return OddsFetchResult(events=[])

        url = f"{settings.odds_api_base_url}/sports/{sport_key}/odds"
        params = {
            "apiKey": settings.odds_api_key,
            "regions": regions if regions is not None else settings.odds_api_regions,
            "markets": markets if markets is not None else settings.odds_api_markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if event_ids:
            params["eventIds"] = event_ids
            
        configured_books = bookmakers if bookmakers is not None else settings.odds_api_bookmakers
        if configured_books.strip():
            params["bookmakers"] = configured_books

        attempts = max(1, settings.odds_api_retry_attempts)
        backoff_base = max(0.1, settings.odds_api_retry_backoff_seconds)
        backoff_cap = max(backoff_base, settings.odds_api_retry_backoff_max_seconds)

        response: httpx.Response | None = None
        payload: object | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                self._record_success()
                break
            except (httpx.HTTPError, ValueError):
                self._record_failure()
                logger.warning(
                    "Odds API fetch attempt failed",
                    exc_info=True,
                    extra={
                        "attempt": attempt,
                        "attempts_total": attempts,
                        "consecutive_failures": self._consecutive_failures,
                    },
                )
                if attempt >= attempts or self._is_circuit_open(datetime.now(UTC)):
                    break
                sleep_seconds = min(backoff_cap, backoff_base * (2 ** (attempt - 1)))
                await asyncio.sleep(sleep_seconds)

        if response is None or payload is None:
            logger.error("Odds API fetch failed after retries; continuing cycle with no events")
            return OddsFetchResult(events=[])

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

        now = datetime.now(UTC)
        if self._is_circuit_open(now):
            logger.warning(
                "Odds API circuit is open; skipping history fetch",
                extra={
                    "circuit_open_until": self._circuit_open_until.isoformat()
                    if self._circuit_open_until is not None
                    else None,
                    "consecutive_failures": self._consecutive_failures,
                },
            )
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

        attempts = max(1, settings.odds_api_retry_attempts)
        backoff_base = max(0.1, settings.odds_api_retry_backoff_seconds)
        backoff_cap = max(backoff_base, settings.odds_api_retry_backoff_max_seconds)

        response: httpx.Response | None = None
        payload: object | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                self._record_success()
                break
            except (httpx.HTTPError, ValueError):
                self._record_failure()
                logger.warning(
                    "Odds API history fetch attempt failed",
                    exc_info=True,
                    extra={
                        "attempt": attempt,
                        "attempts_total": attempts,
                        "consecutive_failures": self._consecutive_failures,
                    },
                )
                if attempt >= attempts or self._is_circuit_open(datetime.now(UTC)):
                    break
                sleep_seconds = min(backoff_cap, backoff_base * (2 ** (attempt - 1)))
                await asyncio.sleep(sleep_seconds)

        if response is None or payload is None:
            logger.error("Odds API history fetch failed after retries; continuing with no events")
            return OddsFetchResult(events=[])

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


async def fetch_nba_odds_history(
    *,
    event_id: str,
    markets: list[str],
    regions: str | None = None,
    bookmakers: list[str] | None = None,
    **kwargs,
) -> dict:
    """
    Fetch historical odds snapshots for a single event.

    Returns a raw payload wrapper compatible with ingestion normalization:
    {
        "events": list[dict],
        "history_timestamp": datetime | None,
        "previous_timestamp": datetime | None,
        "next_timestamp": datetime | None,
        "requests_remaining": int | None,
        "requests_used": int | None,
        "requests_last": int | None,
        "requests_limit": int | None,
    }
    """
    sport_key = str(kwargs.get("sport_key", "basketball_nba"))
    endpoint_variant_raw = str(kwargs.get("endpoint_variant", "event"))
    endpoint_variant: Literal["bulk", "event"] = "event"
    if endpoint_variant_raw == "bulk":
        endpoint_variant = "bulk"
    date_value = kwargs.get("date")
    if not isinstance(date_value, datetime):
        raise ValueError("date datetime is required for historical odds fetch")

    bookmakers_csv = None
    if bookmakers:
        normalized = [book.strip() for book in bookmakers if isinstance(book, str) and book.strip()]
        bookmakers_csv = ",".join(normalized) if normalized else None

    markets_csv = ",".join([market.strip() for market in markets if market.strip()])
    client = OddsApiClient()
    result = await client.fetch_nba_odds_history(
        sport_key=sport_key,
        endpoint_variant=endpoint_variant,
        event_id=event_id,
        markets=markets_csv,
        regions=regions,
        bookmakers=bookmakers_csv,
        date=date_value,
    )
    return {
        "events": result.events,
        "history_timestamp": result.history_timestamp,
        "previous_timestamp": result.previous_timestamp,
        "next_timestamp": result.next_timestamp,
        "requests_remaining": result.requests_remaining,
        "requests_used": result.requests_used,
        "requests_last": result.requests_last,
        "requests_limit": result.requests_limit,
    }
