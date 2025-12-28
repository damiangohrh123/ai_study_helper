
import os
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

app = FastAPI()

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

llm = ChatOpenAI(
    model="gpt-4o",  # Use "gpt-4o" for vision and text
    openai_api_key=OPENAI_API_KEY
)


# SQLAlchemy models
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from db import Base, engine, SessionLocal

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    chats = relationship("ChatHistory", back_populates="user")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    sender = Column(String)  # 'user' or 'ai'
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="chats")

# Create tables on startup
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Dependency to get DB session
async def get_db():
    async with SessionLocal() as session:
        yield session

@app.post("/ask")
async def ask(
    message: str = Form(None),
    file: UploadFile = File(None),
    session_id: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified endpoint for text and/or image input. Tracks session_id, stores chat history in DB, and injects recent history for personalization.
    """
    if not session_id:
        return JSONResponse({"error": "session_id is required for personalization."}, status_code=400)

    # Get or create user
    result = await db.execute(select(User).where(User.session_id == session_id))
    user = result.scalars().first()
    if not user:
        user = User(session_id=session_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.last_active = datetime.utcnow()
        await db.commit()

    # Get last 10 chat history for this user
    result = await db.execute(
        select(ChatHistory).where(ChatHistory.user_id == user.id).order_by(ChatHistory.timestamp.desc()).limit(10)
    )
    history_rows = result.scalars().all()[::-1]  # reverse to chronological
    content = []
    for row in history_rows:
        content.append(HumanMessage(content=row.message))

    # Add new user message/image
    if message:
        content.append(HumanMessage(content=message))
        db.add(ChatHistory(user_id=user.id, message=message, sender='user'))
    if file:
        image_bytes = await file.read()
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        image_dict = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
        content.append(HumanMessage(content=[image_dict]))
        db.add(ChatHistory(user_id=user.id, message=f"[Image uploaded: {file.filename}]", sender='user'))
    if not (message or file):
        return JSONResponse({"error": "No input provided."}, status_code=400)
    try:
        response = llm.invoke(content)
        # Store AI response in history
        db.add(ChatHistory(user_id=user.id, message=response.content, sender='ai'))
        await db.commit()
        return {"response": response.content}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
