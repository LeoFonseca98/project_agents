from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.agents.chat_agent import chat
from app.database.connection import get_db
from app.schemas.requests import UserRequest

app = FastAPI(title="Agent Services", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


@app.get("/", response_class=HTMLResponse)
def index():
    return FRONTEND_DIR.joinpath("index.html").read_text(encoding="utf-8")


@app.post("/chat")
def chat_route(request: UserRequest):
    with get_db() as db:
        response = chat(
            text=request.user_input,
            context=request.context,
            db=db,
        )
        return response.model_dump()


@app.get("/health")
def health():
    return {"status": "ok"}