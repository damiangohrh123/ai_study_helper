from pydantic import BaseModel
from datetime import datetime

class UserCreate(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class GoogleLoginRequest(BaseModel):
    token: str

class ChatSessionCreate(BaseModel):
    title: str | None = None

class ChatSessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    summary: str | None = None
    summary_up_to_message_id: int | None = None

    class Config:
        from_attributes = True