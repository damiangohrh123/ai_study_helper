import os
from db import engine, Base
from routes.routes_auth import router as auth_router
from routes.routes_chat import router as chat_router
from fastapi import FastAPI, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from models import User
from deps import get_db
from auth import get_current_user

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers for authentication and chat
app.include_router(auth_router)
app.include_router(chat_router)

# This function runs automatically when the FastAPI app starts.
# It opens a connection to the database engine and creates all tables defined in the SQLAlchemy models (Base.metadata) if they don't already exist.
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)