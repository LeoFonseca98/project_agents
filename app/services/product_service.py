from typing import Any
from app.repositories.product_repository import ProductRepository


def search_products(query: str, db) -> list[dict[str, Any]]:
    repo = ProductRepository(db)
    return repo.search(query)