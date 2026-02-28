import asyncio
import sys

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import get_password_hash

async def create_user(email: str, password: str, tier: str = "free"):
    async with AsyncSessionLocal() as db:
        user = User(
            email=email.lower(),
            password_hash=get_password_hash(password),
            tier=tier,
        )
        db.add(user)
        try:
            await db.commit()
            await db.refresh(user)
            print(f"Successfully created {tier} user:")
            print(f"  ID:    {user.id}")
            print(f"  Email: {user.email}")
            print(f"  Tier:  {user.tier}")
        except Exception as e:
            await db.rollback()
            print(f"Error creating user: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.create_test_user <email> <password> [tier]")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    tier = sys.argv[3] if len(sys.argv) > 3 else "free"
    
    asyncio.run(create_user(email, password, tier))
