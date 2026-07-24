from typing import Any


class ProductRepository:

    def __init__(self, conn):
        self.conn = conn

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()

        words = [w.strip() for w in query.strip().split() if len(w.strip()) > 1]

        if not words:
            return []

        main_word = words[0]
        extra_words = words[1:] if len(words) > 1 else []

        # Monta relevância extra só se tiver palavras adicionais
        if extra_words:
            extra_relevance = ", " + " + ".join(
                f"CASE WHEN unaccent(description) ILIKE unaccent(%s) THEN 1 ELSE 0 END"
                for _ in extra_words
            ) + " as extra_score"
            extra_params_relevance = [f"%{w}%" for w in extra_words]
            order_extra = ", extra_score DESC"
        else:
            extra_relevance = ""
            extra_params_relevance = []
            order_extra = ""

        params = (
            [f"{main_word}%"] +
            extra_params_relevance +
            [f"%{main_word}%"] +
            [limit]
        )

        cursor.execute(
            f"""
            SELECT id, description, unity, brand, model, code,
                CASE WHEN unaccent(description) ILIKE unaccent(%s)
                    THEN 0 ELSE 1 END as starts_with
                {extra_relevance}
            FROM products
            WHERE unaccent(description) ILIKE unaccent(%s)
            ORDER BY starts_with ASC{order_extra}, description ASC
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