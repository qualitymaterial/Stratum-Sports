from datetime import UTC, datetime

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 180):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None:
            return await call_next(request)

        from app.core.config import get_settings
        settings = get_settings()

        source_ip = request.client.host if request.client else "unknown"
        if source_ip in settings.trusted_proxies_list:
            forwarded_for = request.headers.get("X-Forwarded-For")
            client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else source_ip
        else:
            client_ip = source_ip

        now = datetime.now(UTC)
        minute_bucket = now.strftime("%Y%m%d%H%M")
        key = f"ratelimit:{client_ip}:{minute_bucket}"

        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, 70)

            remaining = max(0, self.requests_per_minute - current)
            reset_ts = int(now.replace(second=0, microsecond=0).timestamp()) + 60

            if current > self.requests_per_minute:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                )
            else:
                response = await call_next(request)

            response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_ts)
            return response
        except Exception:
            return await call_next(request)
