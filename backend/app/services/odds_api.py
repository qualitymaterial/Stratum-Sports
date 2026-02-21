import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OddsApiClient:
    async def fetch_nba_odds(self) -> list[dict]:
        if not settings.odds_api_key:
            logger.warning("ODDS_API_KEY missing; skipping polling cycle")
            return []

        url = f"{settings.odds_api_base_url}/sports/basketball_nba/odds"
        params = {
            "apiKey": settings.odds_api_key,
            "regions": "us",
            "markets": "spreads,totals,h2h",
            "oddsFormat": "american",
            "dateFormat": "iso",
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            logger.warning("Unexpected odds payload type", extra={"type": str(type(payload))})
            return []

        return payload
