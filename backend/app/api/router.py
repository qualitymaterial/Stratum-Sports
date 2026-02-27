from fastapi import APIRouter

from app.api.routes import (
    admin,
    admin_kalshi,
    auth,
    auth_discord,
    billing,
    dashboard,
    discord,
    games,
    health,
    intel,
    ops,
    partner,
    public,
    structure,
    watchlist,
    ws,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_kalshi.router, prefix="/admin/kalshi", tags=["admin", "kalshi"])
api_router.include_router(auth_discord.router, prefix="/auth/discord", tags=["auth"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(intel.router, prefix="/intel", tags=["intel"])
api_router.include_router(public.router, prefix="/public", tags=["public"])
api_router.include_router(ops.router, prefix="/ops", tags=["ops"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(discord.router, prefix="/discord", tags=["discord"])
api_router.include_router(structure.router, prefix="/structure", tags=["structure"])
api_router.include_router(partner.router, prefix="/partner", tags=["partner"])
api_router.include_router(ws.router, prefix="/realtime", tags=["realtime"])
