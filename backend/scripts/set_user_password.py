#!/usr/bin/env python3
"""Establece contraseña de un usuario en Neon. Uso: python -m scripts.set_user_password email nueva_password"""
import asyncio
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.infrastructure.database.models import User
from app.infrastructure.database.session import AsyncSessionLocal


async def main() -> None:
    if len(sys.argv) != 3:
        print("Uso: python -m scripts.set_user_password EMAIL NUEVA_PASSWORD")
        sys.exit(1)
    email, password = sys.argv[1], sys.argv[2]
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"No existe usuario: {email}")
            sys.exit(1)
        user.hashed_password = hash_password(password)
        await db.commit()
        print(f"OK: contraseña actualizada para {email}")


if __name__ == "__main__":
    asyncio.run(main())
