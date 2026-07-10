from typing import Any
from app.repositories.service_repository import ServiceRepository


def search_services(query: str, db, category: str = "") -> list[dict[str, Any]]:
    repo = ServiceRepository(db)
    return repo.search_with_supplies(query, category=category)


def get_supplies(sinapi: str, db) -> list[dict[str, Any]]:
    repo = ServiceRepository(db)
    return repo.get_supplies_by_sinapi(sinapi)