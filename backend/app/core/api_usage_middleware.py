"""Middleware that meters API partner key requests on Intel endpoints."""

import logging
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.services.api_usage_tracking import (
    get_cached_soft_limit,
    increment_usage,
)

logger = logging.getLogger(__name__)

METERED_PATH_PREFIX = "/api/v1/intel/"


class ApiUsageTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        settings = get_settings()
        if not settings.api_usage_tracking_enabled:
            return response

        # Only meter API key requests
        auth_method = getattr(request.state, "auth_method", None)
        if auth_method != "api_key":
            return response

        # Only meter Intel endpoints
        if not request.url.path.startswith(METERED_PATH_PREFIX):
            return response

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            return response

        user_id = getattr(request.state, "api_partner_user_id", None)
        key_id = getattr(request.state, "api_partner_key_id", None)
        if not user_id:
            return response

        # ── Per-partner rate limiting (per minute) ──────────────────
        try:
            partner_limit = settings.partner_rate_limit_per_minute
            now = datetime.now(UTC)
            minute_bucket = now.strftime("%Y%m%d%H%M")
            rate_key = f"partner_ratelimit:{user_id}:{minute_bucket}"
            rate_current = await redis.incr(rate_key)
            if rate_current == 1:
                await redis.expire(rate_key, 70)

            rate_remaining = max(0, partner_limit - rate_current)
            rate_reset = int(now.replace(second=0, microsecond=0).timestamp()) + 60

            if rate_current > partner_limit:
                resp = JSONResponse(
                    status_code=429,
                    content={"detail": "Partner rate limit exceeded"},
                )
                resp.headers["X-Partner-RateLimit-Limit"] = str(partner_limit)
                resp.headers["X-Partner-RateLimit-Remaining"] = "0"
                resp.headers["X-Partner-RateLimit-Reset"] = str(rate_reset)
                return resp
        except Exception:
            logger.exception("Partner rate limit check error")
            rate_remaining = None
            rate_reset = None

        # ── Attach partner rate headers to successful responses ─────
        if rate_remaining is not None:
            response.headers["X-Partner-RateLimit-Limit"] = str(settings.partner_rate_limit_per_minute)
            response.headers["X-Partner-RateLimit-Remaining"] = str(rate_remaining)
            response.headers["X-Partner-RateLimit-Reset"] = str(rate_reset)

        # ── Monthly usage tracking (only for 2xx) ──────────────────
        if response.status_code < 200 or response.status_code >= 300:
            return response

        try:
            new_count = await increment_usage(redis, user_id, key_id)

            # Load soft_limit from cache (lazy-fill from DB on miss)
            soft_limit = await get_cached_soft_limit(redis, user_id)
            if soft_limit is None:
                # We don't have a DB session here — cache will be filled on next
                # get_usage_and_limits call or by the flush job. For now, skip headers.
                soft_limit_val = None
            else:
                soft_limit_val = None if soft_limit == -1 else soft_limit

            # Set usage headers
            if soft_limit_val is not None:
                remaining = max(0, soft_limit_val - new_count)
                is_over = new_count > soft_limit_val
                response.headers["X-RateLimit-Limit"] = str(soft_limit_val)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-Usage-Overage"] = str(is_over).lower()
            else:
                response.headers["X-RateLimit-Remaining"] = "unlimited"

        except Exception:
            logger.exception("API usage tracking middleware error")

        return response
