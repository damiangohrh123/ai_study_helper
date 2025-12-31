from pydantic import BaseModel

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
    created_at: str

    class Config:
        orm_mode = True