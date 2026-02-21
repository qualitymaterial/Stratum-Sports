import asyncio
import sys
import argparse
from app.core.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def promote_user(email: str, tier: str | None = None, is_admin: bool | None = None):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return

        if tier:
            user.tier = tier
        if is_admin is not None:
            user.is_admin = is_admin
            
        try:
            await db.commit()
            await db.refresh(user)
            print(f"Successfully updated user {user.email}:")
            print(f"  Tier:     {user.tier}")
            print(f"  Is Admin: {user.is_admin}")
        except Exception as e:
            await db.rollback()
            print(f"Error updating user: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote a user to a specific tier and/or admin status.")
    parser.add_argument("email", help="Email of the user to promote")
    parser.add_argument("--tier", choices=["free", "pro"], help="The tier to set for the user")
    parser.add_argument("--admin", action="store_true", help="Grant admin status")
    parser.add_argument("--no-admin", action="store_false", dest="admin", help="Remove admin status")
    parser.set_defaults(admin=None)

    args = parser.parse_args()
    
    if args.tier is None and args.admin is None:
        print("Please provide at least --tier or --admin flag.")
        sys.exit(1)
        
    asyncio.run(promote_user(args.email, args.tier, args.admin))
