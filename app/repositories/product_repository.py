from typing import Any


class ProductRepository:

    def __init__(self, conn):
        self.conn = conn

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()

        # Usa só as 2 primeiras palavras para busca mais ampla
        words = [w.strip() for w in query.strip().split() if len(w.strip()) > 1]
        words = words[:2]  # máximo 2 palavras

        if not words:
            return []

        conditions = " AND ".join(
            "unaccent(description) ILIKE unaccent(%s)" for _ in words
        )
        params = [f"%{w}%" for w in words] + [limit]

        cursor.execute(
            f"""
            SELECT id, description, unity, brand, model, code
            FROM products
            WHERE {conditions}
            LIMIT %s
            """,
            params,
        )

        rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                "description": row[1],
                "unity": row[2],
                "brand": row[3],
                "model": row[4],
                "code": row[5],
            }
            for row in rows
        ]

    def find_by_id(self, product_id: str) -> dict[str, Any] | None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, description, unity, brand, model, code
            FROM products
            WHERE id = %s::uuid
            """,
            (product_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "description": row[1],
            "unity": row[2],
            "brand": row[3],
            "model": row[4],
            "code": row[5],
        }