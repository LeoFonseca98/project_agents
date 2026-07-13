from typing import Any


class ProductRepository:

    def __init__(self, conn):
        self.conn = conn

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()

        words = [w.strip() for w in query.strip().split() if len(w.strip()) > 1]
        words = words[:2]

        if not words:
            return []

        conditions = " AND ".join(
            "unaccent(description) ILIKE unaccent(%s)" for _ in words
        )
        params = [f"%{w}%" for w in words] + [f"{words[0]}%"] + [limit]

        cursor.execute(
            f"""
            SELECT id, description, unity, brand, model, code,
                CASE WHEN unaccent(description) ILIKE unaccent(%s)
                    THEN 0 ELSE 1 END AS relevance
            FROM products
            WHERE {conditions}
            ORDER BY relevance, description
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