from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)                          # unique user ID
    email = Column(String, unique=True, index=True, nullable=True)              # user's email address
    password_hash = Column(String, nullable=True)                               # hashed password for authentication
    google_id = Column(String, unique=True, index=True, nullable=True)          # Google OAuth ID
    created_at = Column(DateTime, default=datetime.utcnow)                      # account creation timestamp
    last_active = Column(DateTime, default=datetime.utcnow)                     # last active timestamp
    refresh_token = Column(String, nullable=True)                               # refresh token for session management

    chats = relationship("ChatHistory", back_populates="user")                  # user's chat history
    chat_sessions = relationship("ChatSession", back_populates="user")          # user's chat sessions    

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)                          # unique chat session ID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)           # ID of the user who owns this session
    title = Column(String, default="New Chat")                                  # title of the chat session                
    created_at = Column(DateTime, default=datetime.utcnow)                      # session creation timestamp
    summary = Column(Text, nullable=True)                                        # summary of the chat session (for LLM context)

    user = relationship("User", back_populates="chat_sessions")                 # reference to the User
    messages = relationship("ChatHistory", back_populates="chat_session")       # messages in this chat session

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)                                # unique message ID                                   
    user_id = Column(Integer, ForeignKey("users.id"))                                 # ID of the user who sent/received the message
    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)  # ID of the chat session
    message = Column(Text)                                                            # content of the message
    sender = Column(String)                                                           # 'user' or 'ai'
    timestamp = Column(DateTime, default=datetime.utcnow)                             # message timestamp

    user = relationship("User", back_populates="chats")                               # reference to the User
    chat_session = relationship("ChatSession", back_populates="messages")             # reference to the ChatSession
