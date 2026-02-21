import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User

settings = get_settings()
router = APIRouter()

DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"

@router.get("/login")
async def discord_login():
    if not settings.discord_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discord Client ID not configured"
        )
    
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify email",
    }
    from urllib.parse import urlencode
    query_string = urlencode(params)
    auth_url = f"{DISCORD_AUTH_URL}?{query_string}"
    return {"url": auth_url}

@router.post("/callback")
async def discord_callback(
    code: str = Query(...),
    db: AsyncSession = Depends(get_db)
):
    if not settings.discord_client_id or not settings.discord_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discord OAuth not configured"
        )

    # 1. Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange token: {token_resp.text}"
            )
        
        token_data = token_resp.json()
        access_token = token_data["access_token"]

        # 2. Fetch user info
        user_resp = await client.get(
            DISCORD_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch user info from Discord"
            )
        
        discord_user = user_resp.json()
        discord_id = discord_user["id"]
        email = discord_user.get("email")

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Discord account must have a verified email"
            )

    # 3. Create or find user
    stmt = select(User).where((User.discord_id == discord_id) | (User.email == email))
    db_user = (await db.execute(stmt)).scalar_one_or_none()

    if not db_user:
        # New user via Discord
        db_user = User(
            email=email,
            discord_id=discord_id,
            password_hash=None, # Social login
            tier="free",
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
    else:
        # Update existing user with discord_id if not present
        if not db_user.discord_id:
            db_user.discord_id = discord_id
            await db.commit()

    # 4. Generate JWT
    jwt_token = create_access_token(subject=str(db_user.id))
    return {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user": {
            "id": str(db_user.id),
            "email": db_user.email,
            "tier": db_user.tier,
        }
    }
