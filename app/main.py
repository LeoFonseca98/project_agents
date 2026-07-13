from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any, Optional
import json
from datetime import datetime

from app.agents.chat_agent import chat
from app.database.connection import get_db, get_history_db
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


class SaveListRequest(BaseModel):
    engineer_name: str
    items: list[dict[str, Any]]
    total_services: int = 0
    total_products: int = 0
    parent_id: Optional[str] = None


@app.post("/save-list")
def save_list(request: SaveListRequest):
    with get_history_db() as conn:
        cursor = conn.cursor()

        # Se tem parent_id, calcula a versão
        version = 1
        if request.parent_id:
            cursor.execute(
                """
                SELECT COALESCE(MAX(version), 1) + 1
                FROM list_history
                WHERE parent_id = %s OR id = %s::uuid
                """,
                (request.parent_id, request.parent_id),
            )
            row = cursor.fetchone()
            version = row[0] if row else 2

        cursor.execute(
            """
            INSERT INTO list_history (engineer_name, items, total_services, total_products, parent_id, version)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, created_at, version
            """,
            (
                request.engineer_name,
                json.dumps(request.items, ensure_ascii=False),
                request.total_services,
                request.total_products,
                request.parent_id,
                version,
            ),
        )
        row = cursor.fetchone()
        return {
            "id": str(row[0]),
            "created_at": row[1].isoformat(),
            "version": row[2],
        }


@app.get("/history")
def get_history(engineer_name: str = "", show_archived: bool = False):
    with get_history_db() as conn:
        cursor = conn.cursor()

        filters = ["archived = %s"]
        params = [show_archived]

        if engineer_name:
            filters.append("engineer_name ILIKE %s")
            params.append(f"%{engineer_name}%")

        where = " AND ".join(filters)

        cursor.execute(
            f"""
            SELECT id, engineer_name, created_at, items, total_services, total_products,
                   parent_id, version, archived
            FROM list_history
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT 50
            """,
            params,
        )
        rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                "engineer_name": row[1],
                "created_at": row[2].isoformat(),
                "items": row[3],
                "total_services": row[4],
                "total_products": row[5],
                "parent_id": str(row[6]) if row[6] else None,
                "version": row[7],
                "archived": row[8],
            }
            for row in rows
        ]


@app.patch("/history/{list_id}/archive")
def archive_list(list_id: str):
    with get_history_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE list_history
            SET archived = true
            WHERE id = %s::uuid
            RETURNING id
            """,
            (list_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lista não encontrada")
        return {"id": str(row[0]), "archived": True}


@app.patch("/history/{list_id}/unarchive")
def unarchive_list(list_id: str):
    with get_history_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE list_history
            SET archived = false
            WHERE id = %s::uuid
            RETURNING id
            """,
            (list_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Lista não encontrada")
        return {"id": str(row[0]), "archived": False}


@app.get("/history/{list_id}/versions")
def get_versions(list_id: str):
    with get_history_db() as conn:
        cursor = conn.cursor()
        # Busca todas as versões relacionadas
        cursor.execute(
            """
            SELECT id, engineer_name, created_at, total_services, total_products, version, parent_id
            FROM list_history
            WHERE id = %s::uuid OR parent_id = %s::uuid
            ORDER BY version ASC
            """,
            (list_id, list_id),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                "engineer_name": row[1],
                "created_at": row[2].isoformat(),
                "total_services": row[3],
                "total_products": row[4],
                "version": row[5],
                "parent_id": str(row[6]) if row[6] else None,
            }
            for row in rows
        ]


@app.get("/health")
def health():
    return {"status": "ok"}