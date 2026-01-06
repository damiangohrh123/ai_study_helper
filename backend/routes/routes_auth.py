import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from models import User
from schemas import UserCreate, Token, GoogleLoginRequest
from deps import get_db
from auth import get_password_hash, create_access_token
from dotenv import load_dotenv

load_dotenv()

# Create a router for auth-related endpoints. Every route here will start with /auth
router = APIRouter(prefix="/auth", tags=["auth"])

# --- Utility functions ---
async def commit_or_rollback(db: AsyncSession):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

def set_refresh_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=14*24*60*60,  # 14 days
        samesite="lax",
        secure=True
    )

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()

async def get_user_by_google_id(db: AsyncSession, google_id: str):
    result = await db.execute(select(User).where(User.google_id == google_id))
    return result.scalars().first()

async def generate_refresh_token_for_user(db: AsyncSession, user: User):
    user.refresh_token = secrets.token_urlsafe(32)
    await commit_or_rollback(db)
    return user.refresh_token

# --- Routes ---

# Register a new user
@router.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db), response: Response = None):
    if await get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(email=user.email, password_hash=get_password_hash(user.password))
    db.add(new_user)
    await commit_or_rollback(db)
    await db.refresh(new_user)

    refresh_token = await generate_refresh_token_for_user(db, new_user)
    if response:
        set_refresh_cookie(response, refresh_token)

    token = create_access_token({"sub": str(new_user.id)})
    return {"access_token": token, "token_type": "bearer"}

# Login an existing user
@router.post("/google", response_model=Token)
async def google_login(payload: GoogleLoginRequest, db: AsyncSession = Depends(get_db), response: Response = None):
	# Load Google OAuth client ID from environment variables
	GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
	if not GOOGLE_CLIENT_ID:
		raise RuntimeError("GOOGLE_CLIENT_ID not configured")

	# Verify the Google OAuth2 token sent by the client
	try:
		idinfo = id_token.verify_oauth2_token(
			payload.token,              # Google OAuth token sent from frontend
			google_requests.Request(),  # Makes a request to Google to verify the token's signature
			GOOGLE_CLIENT_ID,           # Ensure token is for our app
		)
	except (ValueError, GoogleAuthError):
		raise HTTPException(status_code=401, detail="Invalid Google token")

	# Extract the Google user ID and email from the verified token
	google_id_val = idinfo["sub"]
	email = idinfo.get("email")

	# Find user by Google ID or email
	user = await get_user_by_google_id(db, google_id_val) or await get_user_by_email(db, email)
	if not user:
		user = User(email=email, google_id=google_id_val)
		db.add(user)
	elif not user.google_id:
		user.google_id = google_id_val

	await commit_or_rollback(db)
	await db.refresh(user)

	refresh_token = await generate_refresh_token_for_user(db, user)
	if response:
		set_refresh_cookie(response, refresh_token)

	token = create_access_token({"sub": str(user.id)})
	return {"access_token": token, "token_type": "bearer"}

# Endpoint to refresh access token using refresh token cookie
@router.post("/refresh")
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
	refresh_token = request.cookies.get("refresh_token")
	if not refresh_token:
		raise HTTPException(status_code=401, detail="No refresh token provided")

	result = await db.execute(select(User).where(User.refresh_token == refresh_token))
	user = result.scalars().first()
	if not user:
		raise HTTPException(status_code=401, detail="Invalid refresh token")

	# Optionally: rotate refresh token here for extra security
	access_token = create_access_token({"sub": str(user.id)})
	return {"access_token": access_token}