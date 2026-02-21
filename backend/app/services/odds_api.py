import logging
from dataclasses import dataclass

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


def _parse_header_int(headers: httpx.Headers, key: str) -> int | None:
    raw = headers.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class OddsApiClient:
    async def fetch_nba_odds(self) -> OddsFetchResult:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping polling cycle")
            return OddsFetchResult(events=[])

        url = f"{settings.odds_api_base_url}/sports/basketball_nba/odds"
        params = {
            "apiKey": settings.odds_api_key,
            "regions": settings.odds_api_regions,
            "markets": settings.odds_api_markets,
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if settings.odds_api_bookmakers.strip():
            params["bookmakers"] = settings.odds_api_bookmakers

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            fetch_result = OddsFetchResult(
                events=payload if isinstance(payload, list) else [],
                requests_remaining=_parse_header_int(response.headers, "x-requests-remaining"),
                requests_used=_parse_header_int(response.headers, "x-requests-used"),
                requests_last=_parse_header_int(response.headers, "x-requests-last"),
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
                },
            )

        return fetch_result
