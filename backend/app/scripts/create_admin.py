from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update an admin user")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    return parser.parse_args()


async def upsert_admin(email: str, password: str) -> str:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Email is required")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.email == normalized_email)
        user = (await db.execute(stmt)).scalar_one_or_none()

        action = "updated"
        if user is None:
            user = User(email=normalized_email)
            db.add(user)
            action = "created"

        user.password_hash = get_password_hash(password)
        user.is_admin = True
        user.admin_role = "super_admin"
        user.tier = "pro"
        user.is_active = True

        await db.commit()
        return action


def main() -> int:
    args = parse_args()
    action = asyncio.run(upsert_admin(args.email, args.password))
    print(f"Admin user {action}: {args.email.strip().lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
