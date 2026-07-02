from typing import Any

# Padrões de texto que indicam ruído de outras categorias
NOISE_PATTERNS = [
    "ligação predial",
    "ramal predial",
    "colar de tomada",
    "escavação manual",
    "escavação mecanizada",
]


class ServiceRepository:

    def __init__(self, conn):
        self.conn = conn

    def search_with_supplies(self, text: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Busca serviços ativos pela descrição usando unaccent (ignora acentos).
        Para cada serviço encontrado, busca a composição via código SINAPI.
        """
        cursor = self.conn.cursor()

        # SOLUÇÃO: Mudamos para usar a função POSITION do SQL.
        # POSITION('termo' IN string) > 0 descobre se o termo existe sem usar nenhum caractere '%'!
        noise_conditions = [
            f"AND POSITION(unaccent('{p}') IN unaccent(description)) = 0" 
            for p in NOISE_PATTERNS
        ]
        noise_clauses = " ".join(noise_conditions)

        # Removemos o f-string complexo e usamos os parâmetros estritos do psycopg2
        query_sql = f"""
            SELECT id, description, category, sinapi
            FROM services
            WHERE active = true
              AND unaccent(description) ILIKE unaccent(%s)
              {noise_clauses}
            ORDER BY description
            LIMIT %s
        """

        cursor.execute(query_sql, (f"%{text}%", limit))
        services = cursor.fetchall()

        if not services:
            return []

        # Agrupa insumos por código SINAPI em uma única query
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

        # Monta resultado final mantendo a ordem original
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
        """Busca insumos de uma composição pelo código SINAPI do serviço."""
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