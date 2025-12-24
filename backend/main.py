from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat_endpoint(request: ChatRequest):
    # Placeholder: Echoes the message
    return {"response": f"You said: {request.message}"}

@app.post("/upload-image")
def upload_image(file: UploadFile = File(...)):
    # Placeholder: Accepts image, returns filename
    return {"filename": file.filename, "text": "(OCR not implemented)"}
