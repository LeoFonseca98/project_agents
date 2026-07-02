import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

from app.services.product_service import search_products as _search_products
from app.services.service_service import search_services as _search_services

load_dotenv()
logger = logging.getLogger(__name__)


def execute_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    db,
    state: dict[str, Any],
) -> dict[str, Any]:

    if tool_name == "set_item_list":
        items = tool_args.get("items", [])
        state["pending_items"] = list(items)
        state["total_items"] = len(items)
        return {
            "tool": "lista_registrada",
            "_history_content": json.dumps({
                "registered": len(items),
                "items": items,
            }, ensure_ascii=False),
            "message": f"{len(items)} item(ns) registrado(s).",
        }

    if tool_name == "search_services":
        query = tool_args.get("query", "").strip()

        if not query:
            return {
                "tool": "sem_resultado",
                "found": 0,
                "data": [],
                "_history_content": json.dumps({
                    "error": "Query vazia. Extraia 2-3 palavras-chave do item e tente novamente.",
                }, ensure_ascii=False),
                "message": "Query vazia. Extraia palavras-chave do item e busque novamente.",
            }

        services = _search_services(query, db)
        state["last_services"] = services

        if not services:
            return {
                "tool": "sem_resultado",
                "found": 0,
                "data": [],
                "_history_content": json.dumps({
                    "found": 0,
                    "message": f"Nenhum serviço encontrado para '{query}'.",
                }, ensure_ascii=False),
                "message": f"Nenhum serviço encontrado para '{query}'.",
            }

        return {
            "tool": "buscar_servico",
            "found": len(services),
            "data": services,
            # descrição completa para o Groq conseguir fazer match no confirm_selection
            "_history_content": json.dumps({
                "found": len(services),
                "items": [s["description"] for s in services],
            }, ensure_ascii=False),
            "message": f"Encontrei {len(services)} serviço(s) para '{query}'.",
        }

    if tool_name == "search_products":
        query = tool_args.get("query", "").strip()

        if not query:
            return {
                "tool": "sem_resultado",
                "found": 0,
                "data": [],
                "_history_content": json.dumps({
                    "error": "Query vazia. Extraia 2-3 palavras-chave do insumo e tente novamente.",
                }, ensure_ascii=False),
                "message": "Query vazia. Extraia palavras-chave do insumo e busque novamente.",
            }

        products = _search_products(query, db)
        state["last_products"] = products

        if not products:
            return {
                "tool": "sem_resultado",
                "found": 0,
                "data": [],
                "_history_content": json.dumps({
                    "found": 0,
                    "message": f"Nenhum produto encontrado para '{query}'.",
                }, ensure_ascii=False),
                "message": f"Nenhum produto encontrado para '{query}'. Passe para o próximo insumo.",
            }

        return {
            "tool": "buscar_produto",
            "found": len(products),
            "data": products,
            "_history_content": json.dumps({
                "found": len(products),
                "items": [" ".join(p["description"].split()[:4]) for p in products],
            }, ensure_ascii=False),
            "message": f"Encontrei {len(products)} produto(s) para '{query}'.",
        }

    if tool_name == "confirm_selection":
        item_type = tool_args.get("type", "")
        description = tool_args.get("description", "")

        item = {
            "description": description,
            "type": item_type,
            "status": "confirmado",
        }
        state.setdefault("selected_items", []).append(item)

        # Remove o item dos pendentes de serviço/material
        pending = state.get("pending_items", [])
        desc = description.lower()
        state["pending_items"] = [
            p for p in pending
            if p.lower() not in desc and desc not in p.lower()
        ]

        if item_type == "service":
            last_services = state.get("last_services", [])

            # Match flexível — aceita descrição parcial
            selected_service = next(
                (s for s in last_services if s["description"] == description),
                None
            )
            if not selected_service:
                selected_service = next(
                    (s for s in last_services if description.lower() in s["description"].lower()),
                    None
                )
            if not selected_service:
                selected_service = next(
                    (s for s in last_services if s["description"].lower().startswith(description.lower()[:20])),
                    None
                )

            supplies = []
            if selected_service and selected_service.get("supplies"):
                supplies = selected_service["supplies"]
                state["pending_supplies"] = list(supplies)
                state["current_service"] = selected_service["description"]

            return {
                "tool": "confirmado",
                "data": item,
                "_history_content": json.dumps({
                    "confirmed": description,
                    "next": supplies[0] if supplies else "no supplies",
                }, ensure_ascii=False),
                "message": (
                    f"✅ Serviço registrado. Agora busque produtos para {len(supplies)} insumo(s)."
                    if supplies else
                    "✅ Serviço registrado sem composição."
                ),
            }

        if item_type == "product":
            pending_supplies = state.get("pending_supplies", [])
            if pending_supplies:
                state["pending_supplies"] = pending_supplies[1:]

            remaining = state.get("pending_supplies", [])

            return {
                "tool": "confirmado",
                "data": item,
                "_history_content": json.dumps({
                    "confirmed": description,
                    "next_supply": remaining[0] if remaining else None,
                }, ensure_ascii=False),
                "message": (
                    f"✅ Produto registrado. {len(remaining)} insumo(s) restante(s)."
                    if remaining else
                    "✅ Produto registrado. Composição completa."
                ),
            }

        return {
            "tool": "confirmado",
            "data": item,
            "_history_content": json.dumps({
                "confirmed": description,
                "type": item_type,
            }, ensure_ascii=False),
            "message": f"✅ Registrado: {description}",
        }

    if tool_name == "finish_list":
        selected = state.get("selected_items", [])
        return {
            "tool": "lista_completa",
            "data": selected,
            "_history_content": json.dumps({
                "finished": True,
                "total": len(selected),
            }, ensure_ascii=False),
            "message": f"✅ Lista finalizada com {len(selected)} item(ns).",
        }

    return {
        "tool": "erro",
        "_history_content": json.dumps({"error": f"Tool '{tool_name}' não reconhecida."}),
        "message": f"Tool '{tool_name}' não reconhecida.",
    }