from db import engine, Base
from routes.routes_auth import router as auth_router
from routes.routes_chat import router as chat_router
from routes.routes_progress import router as progress_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Include routers for authentication, chat, and progress/reflection endpoints
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(progress_router)

# This function runs automatically when the FastAPI app starts.
# It opens a connection to the database engine and creates all tables defined in the SQLAlchemy models (Base.metadata) if they don't already exist.
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)