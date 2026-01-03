from fastapi import Request
import os
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from models import User
from schemas import UserCreate, Token, GoogleLoginRequest
from deps import get_db
from auth import (verify_password, get_password_hash, create_access_token)
import secrets
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

router = APIRouter(prefix="/auth", tags=["auth"])

# Register a new user
@router.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db), response: Response = None):
	result = await db.execute(select(User).where(User.email == user.email))
	if result.scalars().first():
		raise HTTPException(status_code=400, detail="Email already registered")

	refresh_token = secrets.token_urlsafe(32)
	new_user = User(email=user.email, password_hash=get_password_hash(user.password), refresh_token=refresh_token)
	db.add(new_user)

	try:
		await db.commit()
		await db.refresh(new_user)
	except IntegrityError:
		await db.rollback()
		raise HTTPException(status_code=400, detail="Registration failed")

	token = create_access_token({"sub": str(new_user.id)})
	if response is not None:
		response.set_cookie(
			key="refresh_token",
			value=refresh_token,
			httponly=True,
			max_age=14*24*60*60,  # 14 days
			samesite="lax",
			secure=True  # Only send over HTTPS
		)
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

	# Check if a user with this Google ID already exists in our database
	result = await db.execute(select(User).where(User.google_id == google_id_val))
	user = result.scalars().first()

	if not user:
		# Try to find user by email
		result_email = await db.execute(select(User).where(User.email == email))
		user_by_email = result_email.scalars().first()
		if user_by_email:
			# Attach google_id to existing user
			user_by_email.google_id = google_id_val
			try:
				await db.commit()
				await db.refresh(user_by_email)
			except IntegrityError:
				await db.rollback()
				raise HTTPException(status_code=400, detail="Google registration failed (attach google_id)")
			user = user_by_email
		else:
			# Create new user
			user = User(email=email, google_id=google_id_val)
			db.add(user)
			try:
				await db.commit()
				await db.refresh(user)
			except IntegrityError:
				await db.rollback()
				raise HTTPException(status_code=400, detail="Google registration failed (new user)")

	# Generate and store a new refresh token
	refresh_token = secrets.token_urlsafe(32)
	user.refresh_token = refresh_token
	await db.commit()
	# Create an access token (JWT) for the user
	token = create_access_token({"sub": str(user.id)})
	if response is not None:
		response.set_cookie(
			key="refresh_token",
			value=refresh_token,
			httponly=True,
			max_age=14*24*60*60,  # 14 days
			samesite="lax",
			secure=True  # Only send over HTTPS
		)
	# Return the access token and token type to the client
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