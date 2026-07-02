from pydantic import BaseModel
from typing import Any


class UserRequest(BaseModel):
    user_input: str
    context: dict[str, Any] | None = None