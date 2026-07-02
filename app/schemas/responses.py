from pydantic import BaseModel
from typing import Any


class StandardResponse(BaseModel):
    status: str
    tool: str
    message: str
    data: list[Any] = []
    context: dict[str, Any] | None = None