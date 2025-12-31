import os
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import User
from deps import get_db

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")  # JWT secret
logger.info("Loaded SECRET_KEY from environment.")
ALGORITHM = "HS256"                                 # JWT signing algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24               # Token validity: 1 day

# Password Hashing Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

# --- Password hashing and verification ---
def get_password_hash(password: str):
    """Hash a plain password"""
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str):
    """Verify plain password against hashed version"""
    return pwd_context.verify(plain, hashed)

# --- JWT Token Creation ---
def create_access_token(data: dict):
    """Create a JWT access token with expiration"""
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Get Current User from Token ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials
    try:
        # Decode token and extract user id
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        logger.debug(f"Token payload: {payload}, user_id: {user_id}")
    except JWTError as e:
        logger.warning(f"JWTError during token decode: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    # Fetch user from DB
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        logger.warning(f"User not found for user_id: {user_id}")
        raise HTTPException(status_code=401, detail="User not found")

    logger.info(f"Authenticated user: {getattr(user, 'email', user.id)}")
    return user
