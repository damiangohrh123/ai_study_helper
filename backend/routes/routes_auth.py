import os
import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from models import User, RefreshToken
from schemas import UserCreate, Token, GoogleLoginRequest
from deps import get_db
from auth import get_password_hash, create_access_token, REFRESH_TOKEN_EXPIRE_SECONDS
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
        secure=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_SECONDS,
        path="/",
    )

# Helper to hash refresh tokens (use SHA-256 for simplicity)
def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()

async def get_user_by_google_id(db: AsyncSession, google_id: str):
    result = await db.execute(select(User).where(User.google_id == google_id))
    return result.scalars().first()

async def generate_refresh_token_for_user(db: AsyncSession, user: User):
	# Generate a new random token
	raw_token = secrets.token_urlsafe(32)
	token_hash = hash_refresh_token(raw_token)
	expires_at = datetime.utcnow() + timedelta(seconds=REFRESH_TOKEN_EXPIRE_SECONDS)

	# Invalidate all previous tokens for this user (optional, for single-session)
	await db.execute(
		RefreshToken.__table__.update().where(RefreshToken.user_id == user.id, RefreshToken.revoked_at == None).values(revoked_at=datetime.utcnow())
	)

	# Store new token
	new_token = RefreshToken(
		user_id=user.id,
		token_hash=token_hash,
		expires_at=expires_at,
		created_at=datetime.utcnow(),
		revoked_at=None
	)
	db.add(new_token)
	await db.commit()
	return raw_token

# --- Routes ---

# Register a new user
@router.post("/register", response_model=Token)
async def register(user: UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    if await get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(email=user.email, password_hash=get_password_hash(user.password))
    db.add(new_user)
    await commit_or_rollback(db)
    await db.refresh(new_user)

    refresh_token = await generate_refresh_token_for_user(db, new_user)
    set_refresh_cookie(response, refresh_token)

    token = create_access_token({"sub": str(new_user.id)})
    return {"access_token": token, "token_type": "bearer"}

# Login an existing user
@router.post("/google", response_model=Token)
async def google_login(payload: GoogleLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
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
	set_refresh_cookie(response, refresh_token)

	token = create_access_token({"sub": str(user.id)})
	return {"access_token": token, "token_type": "bearer"}

# Endpoint to refresh access token using refresh token cookie
@router.post("/refresh")
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
	raw_token = request.cookies.get("refresh_token")
	if not raw_token:
		raise HTTPException(status_code=401, detail="No refresh token provided")
	token_hash = hash_refresh_token(raw_token)
	
	# Find a valid, unexpired, unrevoked refresh token
	now = datetime.utcnow()
	result = await db.execute(
		select(RefreshToken, User)
		.join(User, RefreshToken.user_id == User.id)
		.where(
			RefreshToken.token_hash == token_hash,
			RefreshToken.expires_at > now,
			RefreshToken.revoked_at == None
		)
	)
	row = result.first()
	if not row:
		raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
	refresh_token_obj, user = row

	# Rotate: revoke old token
	refresh_token_obj.revoked_at = now

	# Issue new refresh token
	new_raw_token = secrets.token_urlsafe(32)
	new_token_hash = hash_refresh_token(new_raw_token)
	new_expires_at = now + timedelta(seconds=REFRESH_TOKEN_EXPIRE_SECONDS)
	new_token_obj = RefreshToken(
		user_id=user.id,
		token_hash=new_token_hash,
		expires_at=new_expires_at,
		created_at=now,
		revoked_at=None
	)
	db.add(new_token_obj)
	await db.commit()

	# Set new cookie and return access token as JSON
	access_token = create_access_token({"sub": str(user.id)})
	response = JSONResponse({"access_token": access_token})
	set_refresh_cookie(response, new_raw_token)
	return response