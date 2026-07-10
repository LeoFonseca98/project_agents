from typing import Any


class ServiceRepository:

    def __init__(self, conn):
        self.conn = conn

    def search_with_supplies(self, text: str, limit: int = 5, category: str = "") -> list[dict[str, Any]]:
        cursor = self.conn.cursor()

        words = [w.strip() for w in text.strip().split() if len(w.strip()) > 1]

        if not words:
            return []

        # Uma condição por palavra — todas devem estar presentes (AND)
        word_conditions = " AND ".join(
            "unaccent(description) ILIKE unaccent(%s)" for _ in words
        )
        params = [f"%{w}%" for w in words]

        if category:
            category_filter = "AND unaccent(category) = unaccent(%s)"
            params.append(category)
        else:
            category_filter = ""

        params.append(limit)

        cursor.execute(
            f"""
            SELECT id, description, category, sinapi,
                -- Relevância: menor posição da primeira palavra-chave = mais relevante
                POSITION(unaccent('{words[0]}') IN unaccent(lower(description))) as relevance
            FROM services
            WHERE active = true
            AND {word_conditions}
            {category_filter}
            ORDER BY relevance ASC, description ASC
            LIMIT %s
            """,
            params,
        )

        services = cursor.fetchall()

        if not services:
            return []

        sinapi_map: dict[str, dict] = {}
        for row in services:
            sinapi = row[3]
            if sinapi:
                sinapi_map[sinapi] = {
                    "id": str(row[0]),
                    "description": row[1],
                    "category": row[2],
                    "sinapi": sinapi,
                    "supplies": [],
                }

        if sinapi_map:
            cursor.execute(
                """
                SELECT DISTINCT c.composition_code, s.item_description
                FROM compositions c
                JOIN composition_supplies cs ON cs.composition_id = c.id
                JOIN supplies s ON s.id = cs.supplies_id
                WHERE c.composition_code = ANY(%s)
                  AND s.active = true
                ORDER BY c.composition_code, s.item_description
                """,
                (list(sinapi_map.keys()),),
            )
            for row in cursor.fetchall():
                code, item_desc = row
                if code in sinapi_map:
                    sinapi_map[code]["supplies"].append(item_desc)

        result = []
        for row in services:
            sinapi = row[3]
            if sinapi and sinapi in sinapi_map:
                result.append(sinapi_map[sinapi])
            else:
                result.append({
                    "id": str(row[0]),
                    "description": row[1],
                    "category": row[2],
                    "sinapi": sinapi,
                    "supplies": [],
                })

        return result

    def get_supplies_by_sinapi(self, sinapi: str) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT s.id, s.item_description, s.item_unit
            FROM compositions c
            JOIN composition_supplies cs ON cs.composition_id = c.id
            JOIN supplies s ON s.id = cs.supplies_id
            WHERE c.composition_code = %s
              AND s.active = true
            ORDER BY s.item_description
            """,
            (sinapi,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": str(row[0]),
                "description": row[1],
                "unit": row[2],
            }
            for row in rows
        ]