import os, logging, base64, textwrap, re
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Path, Body
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, desc

import tiktoken
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from collections import deque

from models import User, ChatHistory, ChatSession
from schemas import ChatSessionCreate, ChatSessionOut
from deps import get_db
from auth import get_current_user

from learning import process_learning_message

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

# Token encodings (explicit, robust to model remapping)
encoding_chat = tiktoken.get_encoding("o200k_base")  # gpt-4o
encoding_summary = tiktoken.get_encoding("o200k_base")  # gpt-4o-mini

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
        await file.seek(0)  # Allow file to be re-read later if needed. (seek(0) moves pointer back to start)
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        image_dict = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
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

    # Check for missing session ID
    if session_id is None:
        raise HTTPException(status_code=400, detail="Session ID required.")

    # Check for overly long message
    if message and len(message) > 20_000:
        raise HTTPException(status_code=400, detail="Message too long")

    # Update last active timestamp
    current_user.last_active = datetime.now(timezone.utc)
    await db.commit()

    # Fetch chat session and verify ownership
    chat_session = await get_user_chat_session(session_id, current_user, db)

    # Fetch full chat history for the session
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.chat_session_id == session_id)
        .order_by(ChatHistory.timestamp.asc())
    )
    history_rows = result.scalars().all()

    # Token-aware history window
    max_window_tokens = TOTAL_MODEL_TOKENS - SYSTEM_PROMPT_TOKENS - SUMMARY_MAX_TOKENS - USER_MAX_TOKENS - RESPONSE_RESERVE_TOKENS
    window_rows = deque()
    window_tokens = 0
    for row in reversed(history_rows):
        msg = preprocess_text(row.message or "")
        tokens = encoding_chat.encode(msg)
        if window_tokens + len(tokens) > max_window_tokens:
            break
        window_rows.appendleft(row)
        window_tokens += len(tokens)
    window_rows = list(window_rows)

    # Determine messages for the summary (all messages before the window)
    summary_rows = [r for r in history_rows if r.id < window_rows[0].id] if window_rows else history_rows

    # Track the last summarized message ID and filter new messages for summarization
    last_summarized_id = chat_session.summary_up_to_message_id or 0
    new_messages = [r for r in summary_rows if r.id > last_summarized_id]

    # Call the incremental summarization function if there are new messages
    if new_messages:
        try:
            summary_text, new_last_id = await summarize_incremental(
                session_id, chat_session.summary, last_summarized_id, new_messages, db
            )
            chat_session.summary = summary_text
            chat_session.summary_up_to_message_id = new_last_id
            await db.commit()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")

    # Build LLM content
    content = await build_llm_content(chat_session, window_rows, message, file)
    if len(content) == 1:  # Only system prompt
        raise HTTPException(status_code=400, detail="No input provided.")

    # -------------------- LLM call & save messages --------------------
    try:
        response = await llm.ainvoke(content)
        rows_to_add = []

        if message:
            rows_to_add.append(ChatHistory(
                user_id=current_user.id,
                chat_session_id=session_id,
                message=message,
                sender="user"
            ))

        if file and file.filename:
            rows_to_add.append(ChatHistory(
                user_id=current_user.id,
                chat_session_id=session_id,
                message=f"[Image uploaded: {file.filename}]",
                sender="user"
            ))

        rows_to_add.append(ChatHistory(
            user_id=current_user.id,
            chat_session_id=session_id,
            message=response.content,
            sender="ai"
        ))

        db.add_all(rows_to_add)
        await db.flush()  # Assign IDs

        # Learning analytics only for user message
        if message:
            await process_learning_message(db, current_user.id, message, rows_to_add[0].id)

        await db.commit()
        return {"response": response.content}

    except Exception as e:
        logger.error(f"LLM call failed: {e}", exc_info=True)
        return JSONResponse(
            {"error": "AI service is currently unavailable. Please try again later."},
            status_code=500,
        )