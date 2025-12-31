import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
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
	GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

	idinfo = id_token.verify_oauth2_token(
		payload.token,
		google_requests.Request(),
		GOOGLE_CLIENT_ID,
	)

	google_id_val = idinfo["sub"]
	email = idinfo.get("email")

	result = await db.execute(select(User).where(User.google_id == google_id_val))
	user = result.scalars().first()

	if not user:
		user = User(email=email, google_id=google_id_val)
		db.add(user)
		await db.commit()
		await db.refresh(user)

	token = create_access_token({"sub": str(user.id)})
	return {"access_token": token, "token_type": "bearer"}