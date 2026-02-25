import asyncio
import sys
import argparse
from app.core.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def promote_user(
    email: str,
    tier: str | None = None,
    is_admin: bool | None = None,
    admin_role: str | None = None,
):
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
            if is_admin and not user.admin_role:
                user.admin_role = "super_admin"
            if not is_admin:
                user.admin_role = None
        if admin_role is not None:
            user.admin_role = admin_role
            user.is_admin = True
            
        try:
            await db.commit()
            await db.refresh(user)
            print(f"Successfully updated user {user.email}:")
            print(f"  Tier:     {user.tier}")
            print(f"  Is Admin: {user.is_admin}")
            print(f"  Role:     {user.admin_role}")
        except Exception as e:
            await db.rollback()
            print(f"Error updating user: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote a user to a specific tier and/or admin status.")
    parser.add_argument("email", help="Email of the user to promote")
    parser.add_argument("--tier", choices=["free", "pro"], help="The tier to set for the user")
    parser.add_argument("--admin", action="store_true", help="Grant admin status")
    parser.add_argument("--no-admin", action="store_false", dest="admin", help="Remove admin status")
    parser.add_argument(
        "--admin-role",
        choices=["super_admin", "ops_admin", "support_admin", "billing_admin"],
        help="Set explicit admin role (also grants admin access)",
    )
    parser.set_defaults(admin=None)

    args = parser.parse_args()
    
    if args.tier is None and args.admin is None and args.admin_role is None:
        print("Please provide at least --tier, --admin, or --admin-role flag.")
        sys.exit(1)
        
    asyncio.run(promote_user(args.email, args.tier, args.admin, args.admin_role))
