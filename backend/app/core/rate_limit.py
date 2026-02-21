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

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        minute_bucket = datetime.now(UTC).strftime("%Y%m%d%H%M")
        key = f"ratelimit:{client_ip}:{minute_bucket}"

        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, 70)
            if current > self.requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                )
        except Exception:
            return await call_next(request)

        return await call_next(request)
