from db import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession

# Dependency function to provide a database session to FastAPI routes
async def get_db():
    async with SessionLocal() as session:  # Open a new async session (workspace) using SessionLocal
        yield session                      # Yield the session to the route, then automatically close it after request