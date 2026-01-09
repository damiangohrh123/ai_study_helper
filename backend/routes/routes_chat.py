import os, logging, base64, textwrap, re
from datetime import datetime

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Path, Body
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

import tiktoken
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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

# Main chat model (gpt-4o)
llm = ChatOpenAI(
    model="gpt-4o",
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# Cheap summarization model (gpt-4o-mini)
llm_summarize = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# Token encodings
encoding_chat = tiktoken.encoding_for_model("gpt-4o")
encoding_summary = tiktoken.encoding_for_model("gpt-4o-mini")

# Token Limits
TOTAL_MODEL_TOKENS = 8000
SYSTEM_PROMPT_TOKENS = 200
SUMMARY_MAX_TOKENS = 500
USER_MAX_TOKENS = 2000
RESPONSE_RESERVE_TOKENS = 1000


# ------------------------------------------------ Helpers ------------------------------------------------ #
async def get_user_chat_session(session_id: int, user: User, db: AsyncSession):
    """Fetch a chat session by ID for a user; raises 404 if not found."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session

def preprocess_text(text):
    """Clean and normalize text for LLM input (removes non-printable chars, trims whitespace, collapses spaces/newlines)."""
    if not text:
        return ''
    text = ''.join(c for c in text if c.isprintable())            # Remove non-printable characters
    text = re.sub(r'[ \t]+', ' ', text)                           # Collapse multiple spaces (but preserve newlines)
    text = re.sub(r'\n{3,}', '\n\n', text)                        # Collapse 3+ newlines to 2 newlines
    text = '\n'.join(line.strip() for line in text.splitlines())  # Remove leading/trailing whitespace on each line
    return text.strip()                                           # Remove leading/trailing whitespace overall

async def summarize_incremental(
    session_id,                  # Identifies which chat this summary belongs to
    last_summary,                # The previous summary text
    last_summary_id,             # The message ID up to which the last summary was made
    new_messages,                # A list of new ChatHistory rows that happened after the last summary
    db: AsyncSession             # Database session
):
    """Incrementally update a chat session summary with new messages using the summarization LLM."""
    # If there are no new messages, do nothing
    if not new_messages:
        return last_summary, last_summary_id

    # Concatenate only the new messages
    new_text = "\n".join(f"{row.sender}: {preprocess_text(row.message or '')}" for row in new_messages)

    # System prompt for summary constraints
    system_prompt = SystemMessage(content=textwrap.dedent(f"""
        You are a chat memory assistant. Update the running summary of a conversation by incorporating the new messages below into the previous summary. 
        - Keep the summary concise (max {SUMMARY_MAX_TOKENS} tokens)
        - Only include key facts, questions, and answers
        - Do not repeat information
        - Use neutral, factual language
        - If the previous summary is empty, create a new summary
        - If the new messages are trivial, you may keep the summary unchanged
    """))

    # Compose the prompt
    prompt = (
        f"Previous summary:\n{last_summary or '[empty]'}\n\n"
        f"New messages:\n{new_text}\n\n"
        f"Update the summary to include the new messages. Limit to 3-5 sentences."
    )

    # Call the LLM
    response = await llm_summarize.ainvoke([system_prompt, HumanMessage(content=prompt)])
    
    # Truncate summary to SUMMARY_MAX_TOKENS if needed
    summary = response.content.strip()
    tokens = encoding_summary.encode(summary)
    if len(tokens) > SUMMARY_MAX_TOKENS:
        summary = encoding_summary.decode(tokens[:SUMMARY_MAX_TOKENS]) + '...'
    return summary, new_messages[-1].id

# Helper to build LLM content window
async def build_llm_content(chat_session, window_rows, user_msg=None, file=None):
    """Build the list of messages for the LLM, including system prompt, conversation summary, history, user input, and optional file."""
    content = []

    # System prompt
    content.append(SystemMessage(content=textwrap.dedent("""
        You are a helpful tutor.
        Formatting rules:
        - Inline math: $a^2 + b^2 = c^2$
        - Display math: $$ E = mc^2 $$
        - Never use \\( \\) or \\[ \\]
        - Never bold math
        - LaTeX must compile
        - If no math is needed, answer normally
    """)))

    # Summary
    if chat_session.summary:
        content.append(SystemMessage(content=f"Summary of previous conversation: {chat_session.summary}"))

    # Window messages
    for row in window_rows:
        msg = preprocess_text(row.message or "")
        if not msg:
            continue
        sender = (row.sender or "").lower()
        if sender == "user":
            content.append(HumanMessage(content=msg))
        elif sender in ("ai", "assistant", "bot"):
            content.append(AIMessage(content=msg))
        else:
            content.append(HumanMessage(content=msg))

    # Current user message
    if user_msg:
        msg = preprocess_text(user_msg)
        if msg:
            tokens = encoding_chat.encode(msg)
            if len(tokens) > USER_MAX_TOKENS:
                msg = encoding_chat.decode(tokens[:USER_MAX_TOKENS]) + "..."
            content.append(HumanMessage(content=msg))

    # File
    if file:
        image_bytes = await file.read()
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        image_dict = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
        content.append(HumanMessage(content=[image_dict]))
    return content

# Helper to save chat messages (user/ai)
async def save_chat_messages(db, session_id, user_id, messages: list[tuple[str, str]]):
    for sender, msg in messages:
        if msg:
            db.add(ChatHistory(
                user_id=user_id,
                chat_session_id=session_id,
                message=msg,
                sender=sender,
            ))
    await db.commit()

# ------------------------------------------------ Chat Session Endpoints ------------------------------------------------ #
@router.post("/sessions", response_model=ChatSessionOut)
async def create_chat_session(
    session: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat session for the current user."""
    new_session = ChatSession(
        user_id=current_user.id, title=session.title or "New Chat"
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session

@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def rename_chat_session(
    session_id: int = Path(...),
    title: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename an existing chat session for the current user."""
    # Fetch session and check ownership
    chat_session = await get_user_chat_session(session_id, current_user, db)
    chat_session.title = title
    await db.commit()
    await db.refresh(chat_session)
    return chat_session

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a chat session and all its messages for the current user."""
    # Fetch session and check ownership
    chat_session = await get_user_chat_session(session_id, current_user, db)
    # Delete all chat history for this session
    await db.execute(
        delete(ChatHistory).where(ChatHistory.chat_session_id == session_id)
    )
    await db.delete(chat_session)
    await db.commit()
    return {"success": True}

@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """List all chat sessions for the current user, ordered by creation date descending."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return sessions

@router.get("/history")
async def get_chat_history(
    session_id: int = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve chat history for the current user. Can filter by session ID."""
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
            "timestamp": row.timestamp.isoformat(),
        }
        for row in history
    ]


# ------------------------------------------------ Ask Endpoint ------------------------------------------------ #
@router.post("/ask")
async def ask(
    message: str = Form(None),
    file: UploadFile = File(None),
    session_id: int = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message (and optional file) to the AI for a specific chat session."""
    # Update last active timestamp
    current_user.last_active = datetime.utcnow()
    await db.commit()

    # 1. Build chat history content (token-aware trimming + rolling summary)
    if session_id is None:
        return JSONResponse({"error": "Session ID required."}, status_code=400)

    # Fetch session and check ownership
    try:
        chat_session = await get_user_chat_session(session_id, current_user, db)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    # Fetch all messages for this session
    query = select(ChatHistory).where(ChatHistory.chat_session_id == session_id).order_by(ChatHistory.timestamp.asc())
    result = await db.execute(query)
    history_rows = result.scalars().all()

    # Determine window by tokens
    max_window_tokens = TOTAL_MODEL_TOKENS - SYSTEM_PROMPT_TOKENS - SUMMARY_MAX_TOKENS - USER_MAX_TOKENS - RESPONSE_RESERVE_TOKENS
    window_rows = []
    window_tokens = 0
    for row in reversed(history_rows):
        msg = preprocess_text(row.message or "")
        tokens = encoding_chat.encode(msg)
        if window_tokens + len(tokens) > max_window_tokens:
            break
        window_rows.insert(0, row)
        window_tokens += len(tokens)

    # Everything before the window is for summary
    if window_rows:
        window_start_id = window_rows[0].id
        summary_rows = [r for r in history_rows if r.id < window_start_id]
    else:
        summary_rows = history_rows

    # Incremental summarization: only summarize new messages
    last_summarized_id = chat_session.summary_up_to_message_id or 0
    new_messages = [r for r in summary_rows if r.id > last_summarized_id]
    if new_messages:
        try:
            summary_text, new_last_id = await summarize_incremental(
                session_id,
                chat_session.summary,
                last_summarized_id,
                new_messages,
                db
            )
            chat_session.summary = summary_text
            chat_session.summary_up_to_message_id = new_last_id
            await db.commit()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")

    # Build content for LLM using helper
    content = await build_llm_content(chat_session, window_rows, message, file)
    if len(content) == 1:  # Only system prompt, no user input
        return JSONResponse({"error": "No input provided."}, status_code=400)

    # Invoke the model and save messages to DB
    try:
        response = await llm.ainvoke(content)
        await save_chat_messages(
            db,
            session_id,
            current_user.id,
            [
                ("user", message),
                ("user", f"[Image uploaded: {file.filename}]" if file else None),
                ("ai", response.content),
            ]
        )
        return {"response": response.content}

    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        return JSONResponse(
            {"error": "AI service is currently unavailable. Please try again later."},
            status_code=500,
        )