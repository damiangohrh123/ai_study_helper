
import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

app = FastAPI()

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

llm = ChatOpenAI(
    model="gpt-4o",  # Use "gpt-4o" for vision and text
    openai_api_key=OPENAI_API_KEY
)

@app.post("/ask")
async def ask(
    message: str = Form(None),
    file: UploadFile = File(None)
):
    """
    Unified endpoint for text and/or image input. Sends both to GPT-4o via LangChain.
    """
    content = []
    if message:
        content.append(HumanMessage(content=message))
    if file:
        image_bytes = await file.read()
        # LangChain expects images as dict: {"type": "image_url", "image_url": "data:image/png;base64,..."}
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        mime = file.content_type or "image/png"
        image_dict = {"type": "image_url", "image_url": f"data:{mime};base64,{b64}"}
        content.append(HumanMessage(content=[image_dict]))
    if not content:
        return JSONResponse({"error": "No input provided."}, status_code=400)
    try:
        response = llm.invoke(content)
        return {"response": response.content}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
