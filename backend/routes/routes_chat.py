import base64
import logging
import os
import re
import textwrap
from dotenv import load_dotenv
from fastapi import (APIRouter, HTTPException, UploadFile, Depends, Body, Path, Query, Form, File)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Union
import tiktoken
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from deps import get_db
from auth import get_current_user
from models import ChatHistory, ChatSession, User

# ------------------------------------------------ App Setup ------------------------------------------------ #
load_dotenv(override=False)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ------------------------------------------------ LLM Models ------------------------------------------------ #
# Initialize the main language model (GPT-4o) for general chat/response tasks
llm = ChatOpenAI(
    model="gpt-4o",
    openai_api_key=os.getenv("OPENAI_API_KEY")
)
# Initialize a smaller GPT-4o variant for summarization tasks
llm_summarize = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# ------------------------------------------------ Token Handling ------------------------------------------------ #
encoding_chat = tiktoken.get_encoding("o200k_base")
encoding_summary = tiktoken.get_encoding("o200k_base")
TOTAL_MODEL_TOKENS = 8000
SUMMARY_MAX_TOKENS = 500
USER_MAX_TOKENS = 2000
RESPONSE_RESERVE_TOKENS = 1000

# ------------------------------------------------ Helpers ------------------------------------------------ #
async def get_user_chat_session(session_id: int, user: User, db: AsyncSession) -> ChatSession:
    """
    Return a chat session by ID, ensuring it belongs to the given user.
    Raises 404 if the session does not exist.
    """
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session

def preprocess_text(text: Optional[str]) -> str:
    """
    Clean and normalize input text for consistent processing.
    """
    if not text:
        return ""
    text = "".join(c for c in text if c.isprintable())            # Remove non-printable characters
    text = re.sub(r"[ \t]+", " ", text)                           # Collapse multiple spaces or tabs into a single space
    text = re.sub(r"\n{3,}", "\n\n", text)                        # Limit excessive newlines to a maximum of two
    text = "\n".join(line.strip() for line in text.splitlines())  # Strip leading and trailing whitespace from each line
    return text.strip()                                           # Remove leading and trailing whitespace from the full text

async def summarize_incremental(
    last_summary: Optional[str],
    last_summary_id: int,
    new_messages: List[ChatHistory],
) -> tuple[str, int]:
    """
    Incrementally update a chat summary using only new messages.
    """

    # If there are no new messages, return the existing summary unchanged
    if not new_messages:
        return last_summary, last_summary_id

    # Format new messages as "sender: message" and preprocess their text
    new_text = "\n".join(
        f"{m.sender}: {preprocess_text(m.message or '')}"
        for m in new_messages
    )

    system_prompt = SystemMessage(content=textwrap.dedent(f"""
        You are a chat memory assistant.
        Keep summaries under {SUMMARY_MAX_TOKENS} tokens.
        Only retain key facts and conclusions.
    """))

    prompt = (
        f"Previous summary:\n{last_summary or '[empty]'}\n\n"
        f"New messages:\n{new_text}"
    )

    response = await llm_summarize.ainvoke([
        system_prompt,
        HumanMessage(content=prompt)
    ])

    summary = response.content.strip()

    # Enforce token limit by truncating if necessary
    tokens = encoding_summary.encode(summary)
    if len(tokens) > SUMMARY_MAX_TOKENS:
        summary = encoding_summary.decode(tokens[:SUMMARY_MAX_TOKENS]) + "..."

    # Return the updated summary and the ID of the last processed message
    return summary, new_messages[-1].id

def build_system_prompt() -> SystemMessage:
    return SystemMessage(content=textwrap.dedent("""
        You are a helpful tutor.
        Default to clear, step-by-step explanations
        unless the user explicitly asks for brevity.

        Formatting rules:
        - Inline math: $a^2 + b^2 = c^2$
        - Display math: $$ E = mc^2 $$
        - Never use \\( \\) or \\[ \\]
        - Never bold math
        - LaTeX must compile
    """))

async def build_history_content(
    chat_session: ChatSession,
    window_rows: List[ChatHistory],
    user_msg: Optional[str],
    file: Optional[UploadFile]
) -> List[Union[SystemMessage, HumanMessage, AIMessage]]:
    """
    Build the message history sent to the LLM, including summary, context, and new input.
    """

    # Initialize the message list
    content: List[Union[SystemMessage, HumanMessage, AIMessage]] = []

    # Add the system message containing the summarized conversation history
    content.append(SystemMessage(
        content=f"Summary of previous conversation:\n{chat_session.summary or '[empty]'}"
    ))

    # Add recent chat messages (context window)
    for row in window_rows:
        msg = preprocess_text(row.message or "")
        if not msg:
            continue
        if row.sender == "user":
            content.append(HumanMessage(content=msg))
        else:
            content.append(AIMessage(content=msg))

    # Add the current user message, enforcing a token limit
    if user_msg:
        msg = preprocess_text(user_msg)
        tokens = encoding_chat.encode(msg)
        if len(tokens) > USER_MAX_TOKENS:
            msg = encoding_chat.decode(tokens[:USER_MAX_TOKENS]) + "..."
        content.append(HumanMessage(content=msg))

    # If a file is provided, encode it as a base64 image input
    if file:
        image_bytes = await file.read()
        await file.seek(0)
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        content.append(HumanMessage(content=[{
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        }]))

    return content

# ------------------------------------------------ Chat Session Endpoints ------------------------------------------------ #
@router.get("/sessions")
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Return all chat sessions for the current user, newest first.
    """
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return sessions

@router.post("/sessions")
async def create_chat_session(
    title: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new chat session for the current user.
    """
    new_session = ChatSession(
        user_id=current_user.id, title=title or "New Chat"
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session

@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: int = Path(...),
    title: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Rename an existing chat session for the current user.
    """
    session = await get_user_chat_session(session_id, current_user, db)
    session.title = title
    await db.commit()
    await db.refresh(session)
    return session

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a chat session owned by the current user.
    """
    session = await get_user_chat_session(session_id, current_user, db)
    await db.delete(session)
    await db.commit()
    return {"success": True}

# ------------------------------------------------ Chat History Endpoint ------------------------------------------------ #
@router.get("/history")
async def get_chat_history(
    session_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """
    Retrieve the full chat history for a given session for the current user.
    """
    result = await db.execute(
        select(ChatHistory)
        .where(
            ChatHistory.user_id == current_user.id,
            ChatHistory.chat_session_id == session_id
        )
        .order_by(ChatHistory.timestamp.asc())
    )
    history = result.scalars().all()
    return [
        {
            "sender": row.sender,
            "text": row.message,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }
        for row in history
    ]

# ------------------------------------------------ Ask Endpoint ------------------------------------------------ #
@router.post("/ask")
async def ask(
    message: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    session_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Handle a user query (text or file) and return the AI response.
    Stores both the user input and AI reply in chat history.
    """
    if not message and not file:
        raise HTTPException(status_code=400, detail="No input provided.")

    chat_session = await get_user_chat_session(session_id, current_user, db)

    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.chat_session_id == session_id)
        .order_by(ChatHistory.timestamp.asc())
    )
    history_rows = result.scalars().all()

    # Determine if user is requesting a quiz question
    quiz_mode = message and message.strip().lower() in ['generate_quiz', 'next_question']

    if quiz_mode:
        # Check if last message is an unanswered quiz question
        last_msg = history_rows[-1] if history_rows else None
        if last_msg and last_msg.sender == 'ai' and getattr(last_msg, 'message_type', 'text') == 'quiz_question':
            return {"response": "Please answer the previous quiz question before requesting a new one.", "message_type": "quiz_lock"}
        # Build prompt for **single-question quiz**
        system_prompt = SystemMessage(content=textwrap.dedent("""
            You are a friendly tutor generating **one quiz question** based on the conversation so far.
            - Keep the question clear and concise.
            - Include conceptual or calculation questions.
            - Wait for the user's answer before giving feedback.
            - Feedback should be encouraging and educational.
        """))
        # Combine with chat history for context
        content = [system_prompt]
        content.extend(await build_history_content(chat_session, history_rows, None, file))
    else:
        content = [build_system_prompt()]
        content.extend(await build_history_content(chat_session, history_rows, message, file))

    try:
        response = await llm.ainvoke(content)

        # Prepare new ChatHistory entries to store in DB
        rows_to_add = []

        # Store user text input if provided
        if message:
            # If the previous message was a quiz question, tag this as a quiz answer
            last_msg = history_rows[-1] if history_rows else None
            msg_type = 'quiz_answer' if last_msg and last_msg.sender == 'ai' and getattr(last_msg, 'message_type', 'text') == 'quiz_question' else 'text'
            rows_to_add.append(ChatHistory(
                user_id=current_user.id,
                chat_session_id=session_id,
                message=message,
                sender="user",
                message_type=msg_type
            ))

        # Store a note for uploaded file if provided
        if file and file.filename:
            rows_to_add.append(ChatHistory(
                user_id=current_user.id,
                chat_session_id=session_id,
                message=f"[Image uploaded: {file.filename}]",
                sender="user",
                message_type="text"
            ))

        # Store AI response
        ai_msg_type = 'quiz_question' if quiz_mode else 'text'
        rows_to_add.append(ChatHistory(
            user_id=current_user.id,
            chat_session_id=session_id,
            message=response.content,
            sender="ai",
            message_type=ai_msg_type
        ))

        # Add all new history entries to the database and commit
        db.add_all(rows_to_add)
        await db.commit()
        return {"response": response.content, "message_type": ai_msg_type}

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=500, detail="AI response failed.")