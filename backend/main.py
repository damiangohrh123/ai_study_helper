import os
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from db import Base, engine, SessionLocal

# --- AUTH ENDPOINTS ---
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel


# Load environment variables
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

# JWT and password hashing setup
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
# Create tables on startup

# Dependency to get DB session (must be above all endpoints that use it)
async def get_db():
    async with SessionLocal() as session:
        yield session

class UserCreate(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

@app.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_pw = get_password_hash(user.password)
    new_user = User(email=user.email, password_hash=hashed_pw)
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Registration failed")
    token = create_access_token({"sub": str(new_user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    if not user or not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


# --- Google OAuth2 login ---
class GoogleLoginRequest(BaseModel):
    token: str

@app.post("/google-login", response_model=Token)
async def google_login(payload: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        # Specify your Google OAuth2 client ID here
        GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
        idinfo = id_token.verify_oauth2_token(payload.token, google_requests.Request(), GOOGLE_CLIENT_ID)
        google_id_val = idinfo["sub"]
        email = idinfo.get("email")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")

    # Upsert user by google_id
    result = await db.execute(select(User).where(User.google_id == google_id_val))
    user = result.scalars().first()
    if not user:
        # If not found, try by email (for account linking)
        if email:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user:
                user.google_id = google_id_val
            else:
                user = User(email=email, google_id=google_id_val)
        else:
            user = User(google_id=google_id_val)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

llm = ChatOpenAI(
    model="gpt-4o",  # Use "gpt-4o" for vision and text
    openai_api_key=OPENAI_API_KEY
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=True)
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
