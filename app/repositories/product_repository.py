from typing import Any


class ProductRepository:

    def __init__(self, conn):
        self.conn = conn

    def search(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        """Busca produtos por descrição usando unaccent para ignorar acentos."""

        cursor = self.conn.cursor()
        words = [w for w in text.strip().split() if len(w) > 2]

        if not words:
            return []

        # Primeira palavra como prefixo, demais como filtro
        first = words[0]
        rest = words[1:]

        conditions = ["unaccent(description) ILIKE unaccent(%s)"]
        params: list[Any] = [f"{first}%"]

        for w in rest:
            conditions.append("unaccent(description) ILIKE unaccent(%s)")
            params.append(f"%{w}%")

        where = " AND ".join(conditions)
        params.append(limit)

        cursor.execute(
            f"""
            SELECT id, description, unity, brand, model, code
            FROM products
            WHERE {where}
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