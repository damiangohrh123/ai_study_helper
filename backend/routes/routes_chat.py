import os, logging, base64
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.responses import JSONResponse
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from datetime import datetime

from models import User, ChatHistory, ChatSession
from schemas import ChatSessionCreate, ChatSessionOut
from deps import get_db
from auth import get_current_user

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a router for chat-related endpoints. Every route here will start with /chat
router = APIRouter(prefix="/chat", tags=["chat"])

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o", openai_api_key=os.getenv("OPENAI_API_KEY"))

# ---------------- Chat Session Endpoints ---------------- #

# Endpoint to create a new chat session
@router.post("/sessions", response_model=ChatSessionOut)
async def create_chat_session(
	session: ChatSessionCreate,
	db: AsyncSession = Depends(get_db),
	current_user: User = Depends(get_current_user)
):
	new_session = ChatSession(user_id=current_user.id, title=session.title or "New Chat")
	db.add(new_session)
	await db.commit()
	await db.refresh(new_session)
	return new_session

# Endpoint to list all chat sessions for the user
@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
	db: AsyncSession = Depends(get_db),
	current_user: User = Depends(get_current_user)
):
	result = await db.execute(
		select(ChatSession).where(ChatSession.user_id == current_user.id).order_by(ChatSession.created_at.desc())
	)
	sessions = result.scalars().all()
	return sessions

# Endpoint to get chat history, optionally filtered by session_id
@router.get("/history")
async def get_chat_history(
	session_id: int = Query(None),
	current_user: User = Depends(get_current_user),
	db: AsyncSession = Depends(get_db)
):
	query = select(ChatHistory).where(ChatHistory.user_id == current_user.id)
	if session_id is not None:
		query = query.where(ChatHistory.chat_session_id == session_id)
	query = query.order_by(ChatHistory.timestamp.asc())
	result = await db.execute(query)
	history = result.scalars().all()
	return [
		{
			"sender": row.sender,
			"text": row.message,
			"timestamp": row.timestamp.isoformat()
		}
		for row in history
	]

# ---------------- Ask Endpoint ---------------- #

@router.post("/ask")
async def ask(
    message: str = Form(None),
    file: UploadFile = File(None),
    session_id: int = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Require authentication for all chat endpoints
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required.")

	# Update last active timestamp
    current_user.last_active = datetime.utcnow()
    await db.commit()

    # 1. Build chat history content
    query = select(ChatHistory).where(ChatHistory.user_id == current_user.id)
    if session_id is not None:
        query = query.where(ChatHistory.chat_session_id == session_id)
    query = query.order_by(ChatHistory.timestamp.desc()).limit(10)
    result = await db.execute(query)
    history_rows = result.scalars().all()[::-1]
    content = [HumanMessage(content=row.message) for row in history_rows]

    if message:
        content.append(HumanMessage(content=message))
    if file:
        image_bytes = await file.read()
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        image_dict = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
        content.append(HumanMessage(content=[image_dict]))
    if not content:
        return JSONResponse({"error": "No input provided."}, status_code=400)

    # 2. Prepend SystemMessage for KaTeX-ready formatting
    system_prompt = SystemMessage(content=
		"""
		You are a helpful tutor for students.

		Rules:
		- Inline math MUST use single dollar signs, e.g., $a^2 + b^2 = c^2$
		- Display equations MUST use double dollar signs on their own lines, e.g.,

		$$
		E = mc^2
		$$

		- Do NOT use \\( \\) or \\[ \\] for math
		- Ensure LaTeX is valid and compilable
		- If no math is present, just answer normally
		"""
	)
    content = [system_prompt] + content

    # 3. Invoke the model
    try:
        response = llm.invoke(content)

        # Save messages to DB
        if message:
            db.add(ChatHistory(user_id=current_user.id, chat_session_id=session_id, message=message, sender='user'))
        if file:
            db.add(ChatHistory(user_id=current_user.id, chat_session_id=session_id, message=f"[Image uploaded: {file.filename}]", sender='user'))
        db.add(ChatHistory(user_id=current_user.id, chat_session_id=session_id, message=response.content, sender='ai'))
        await db.commit()

        return {"response": response.content}
    
    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        return JSONResponse({"error": "AI service is currently unavailable. Please try again later."}, status_code=500)