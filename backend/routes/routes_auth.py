import os
from fastapi import APIRouter, Depends, HTTPException
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
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

router = APIRouter(prefix="/auth", tags=["auth"])

# Register a new user
@router.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
	result = await db.execute(select(User).where(User.email == user.email))
	if result.scalars().first():
		raise HTTPException(status_code=400, detail="Email already registered")

	new_user = User(email=user.email, password_hash=get_password_hash(user.password))
	db.add(new_user)

	try:
		await db.commit()
		await db.refresh(new_user)
	except IntegrityError:
		await db.rollback()
		raise HTTPException(status_code=400, detail="Registration failed")

	token = create_access_token({"sub": str(new_user.id)})
	return {"access_token": token, "token_type": "bearer"}

# Login an existing user
@router.post("/google", response_model=Token)
async def google_login(payload: GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
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

	# If user does not exist, create a new account (auto-registration)
	if not user:
		user = User(email=email, google_id=google_id_val)
		db.add(user)
		try:
			await db.commit()
			await db.refresh(user)
		except IntegrityError:
			await db.rollback()
			raise HTTPException(status_code=400, detail="Google registration failed")

	# Create an access token (JWT) for the user
	token = create_access_token({"sub": str(user.id)})

	# Return the access token and token type to the client
	return {"access_token": token, "token_type": "bearer"}