import os
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.responses import JSONResponse
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from models import User, ChatHistory
from deps import get_db
from auth import get_current_user

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a router for chat-related endpoints. Every route here will start with /chat
router = APIRouter(prefix="/chat", tags=["chat"])

# Load API key and initialize LLM client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o", openai_api_key=OPENAI_API_KEY)

@router.get("/history")
async def get_chat_history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
	result = await db.execute(
		select(ChatHistory).where(ChatHistory.user_id == current_user.id).order_by(ChatHistory.timestamp.asc())
	)
	history = result.scalars().all()
	return [
		{
			"sender": row.sender,
			"text": row.message,
			"timestamp": row.timestamp.isoformat()
		}
		for row in history
	]

@router.post("/ask")
async def ask(
	message: str = Form(None),
	file: UploadFile = File(None),
	db: AsyncSession = Depends(get_db),
	current_user: User = Depends(get_current_user)
):
	# Only allow authenticated users
	user = current_user
	from datetime import datetime
	user.last_active = datetime.utcnow()
	await db.commit()

	result = await db.execute(
		select(ChatHistory).where(ChatHistory.user_id == user.id).order_by(ChatHistory.timestamp.desc()).limit(10)
	)
	history_rows = result.scalars().all()[::-1]
	content = [HumanMessage(content=row.message) for row in history_rows]

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
		db.add(ChatHistory(user_id=user.id, message=response.content, sender='ai'))
		await db.commit()
		return {"response": response.content}
	except Exception as e:
		logger.error(f"LLM call failed: {e}", exc_info=True)
		# Optionally, return a generic error message to the user
		return JSONResponse({"error": "AI service is currently unavailable. Please try again later."}, status_code=500)
