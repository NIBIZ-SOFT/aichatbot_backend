import sys
import asyncio
import os
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.all_models import User, UserRole

async def create_super_admin(email, password):
    async with AsyncSessionLocal() as db:
        new_user = User(
            tenant_id=None,
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Platform Super Admin",
            role=UserRole.SUPER_ADMIN,
            department="Platform Operations",
            is_active=True,
            is_online=False
        )
        db.add(new_user)
        await db.commit()
        print(f"Super admin {email} created successfully!")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_super_admin.py <email> <password>")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    asyncio.run(create_super_admin(email, password))
