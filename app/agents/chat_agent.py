import json
import logging
import os
import re
from typing import Any
from groq import Groq
from dotenv import load_dotenv
from app.schemas.responses import StandardResponse
from app.services.service_service import search_services as _search_services
from app.services.product_service import search_products as _search_products

load_dotenv()
logger = logging.getLogger(__name__)

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

CATEGORIES = [
    "ALVENARIA", "CLIMATIZAÇÃO", "COBERTURA",
    "DRENAGEM, OBRAS DE CONTENCAO, POCOS DE VISITA E CAIXAS",
    "ELÉTRICA", "ESTRUTURA METALICA", "FECHAMENTO, VEDAÇÕES E ESQUADRIA",
    "HIDRÁULICA", "HIDROSSANITARIA", "IMPERMEABILIZAÇÃO", "INCENDIO",
    "INFRA-ESTRUTURA", "INSTALAÇÕES PRÓVISORIAS", "JARDINAGEM E URBANISMO",
    "LIMPEZAS", "LOCAÇÃO", "MONTAGEM", "MOVIMENTAÇÃO DE TERRA", "PEDRA",
    "PEDRAS (BANCADAS, DIVISORIAS E REVESTIMENTO)", "PINTURA", "REFRIGERAÇÃO",
    "REVESTIMENTOS", "SERRALHERIA", "SERVIÇOS COMPLEMENTARES",
    "SERVIÇOS GERAIS", "SERVIÇOS PRELIMINARES", "SERVIÇO TERCEIRIZADO",
    "SUPER-ESTRUTURA",
]

STAGE_IDLE = "idle"
STAGE_WAITING_CATEGORY = "waiting_category"
STAGE_WAITING_SERVICE = "waiting_service"
STAGE_WAITING_SUPPLY = "waiting_supply"
STAGE_WAITING_PRODUCT = "waiting_product"
STAGE_WAITING_NEXT = "waiting_next"


def _classify_items(text: str) -> list[dict]:
    try:
        response = _client.chat.completions.create(
            model=_model,
            messages=[{
                "role": "user",
                "content": (
                    "Classifique cada item desta lista de obras.\n\n"
                    "REGRAS:\n"
                    "- service = ação/execução (instalar, assentar, pintar, demolir, executar, construir)\n"
                    "- product = material/ferramenta/insumo (tinta, cabo, lixa, pincel, parafuso, tubo, tomada, fio, cimento, areia, tijolo)\n\n"
                    f"Lista: {text}\n\n"
                    "Retorne APENAS JSON sem markdown:\n"
                    "{\"items\": [{\"name\": \"nome exato\", \"type\": \"service\"}]}"
                )
            }],
            temperature=0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw).get("items", [])
        for item in result:
            t = item.get("type", "").lower()
            item["type"] = "service" if "servi" in t or t == "service" else "product"
        return result
    except Exception as e:
        logger.error(f"Erro ao classificar: {e}")
        items = [i.strip() for i in re.split(r'[,.]', text) if i.strip()]
        return [{"name": i, "type": "service"} for i in items]


def _make_query(text: str) -> str:
    """Extrai palavras-chave para busca."""
    words = text.strip().split()

    if len(words) <= 2:
        return text

    try:
        response = _client.chat.completions.create(
            model=_model,
            messages=[{
                "role": "user",
                "content": (
                    f"Extraia 2-3 palavras-chave do item abaixo para busca em banco de dados. "
                    f"Use APENAS palavras que estão no item original. "
                    f"Sem acentos. Sem palavras novas.\n"
                    f"Item: '{text}'\n"
                    f"Palavras-chave:"
                )
            }],
            temperature=0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().lower()
        return result
    except Exception as e:
        return text


def _process_current_item(state: dict, history: list, db) -> StandardResponse:
    skip_message = state.pop("skip_message", None)
    pending_items = state.get("pending_items", [])
    pending_supplies = state.get("pending_supplies", [])

    # ── Insumos pendentes ────────────────────────────────────────────────────
    if pending_supplies:
        supply = pending_supplies[0]
        query = _make_query(supply)
        products = _search_products(query, db)
        state["last_products"] = products
        state["current_supply"] = supply

        if not products:
            state["pending_supplies"] = pending_supplies[1:]
            if state["pending_supplies"]:
                return _process_current_item(state, history, db)
            else:
                state["stage"] = STAGE_WAITING_NEXT
                return _ask_next(state, history)

        state["stage"] = STAGE_WAITING_SUPPLY
        prefix = f"{skip_message}\n\n" if skip_message else ""
        return StandardResponse(
            status="success",
            tool="buscar_produto",
            message=f"{prefix}Insumo: '{supply}'. Selecione o produto:",
            data=products,
            context={"history": history, "state": state},
        )

    if not pending_items:
        selected = state.get("selected_items", [])
        prefix = f"{skip_message}\n\n" if skip_message else ""
        return StandardResponse(
            status="success",
            tool="lista_completa",
            message=f"{prefix}✅ Lista finalizada com {len(selected)} item(ns).",
            data=selected,
            context={"history": history, "state": state},
        )

    item = pending_items[0]
    item_type = item.get("type", "service")
    item_name = item.get("name", "")

    if item_type == "product":
        query = _make_query(item_name)
        products = _search_products(query, db)
        state["last_products"] = products
        state["current_supply"] = ""

        if not products:
            state["pending_items"] = pending_items[1:]
            return _process_current_item(state, history, db)

        state["stage"] = STAGE_WAITING_PRODUCT
        prefix = f"{skip_message}\n\n" if skip_message else ""
        return StandardResponse(
            status="success",
            tool="buscar_produto",
            message=f"{prefix}Encontrei produtos para '{item_name}'. Selecione:",
            data=products,
            context={"history": history, "state": state},
        )

    selected_category = state.get("selected_category", "")

    if not selected_category:
        state["stage"] = STAGE_WAITING_CATEGORY
        state["category_attempts"] = state.get("category_attempts", 0)
        prefix = f"{skip_message}\n\n" if skip_message else ""
        return StandardResponse(
            status="success",
            tool="selecionar_categoria",
            message=f"{prefix}Qual é a categoria do serviço '{item_name}'?",
            data=[{"name": c} for c in CATEGORIES],
            context={"history": history, "state": state},
        )

    query = _make_query(item_name)
    services = _search_services(query, db, category=selected_category)
    state["last_services"] = services

    if not services:
        attempts = state.get("category_attempts", 0) + 1
        state["category_attempts"] = attempts
        state["selected_category"] = ""

        if attempts >= 3:
            state["category_attempts"] = 0
            pending = state.get("pending_items", [])
            state["pending_items"] = pending[1:] if pending else []
            state["skip_message"] = f"⚠️ '{item_name}' não encontrado em nenhuma categoria. Passando para o próximo item."
            return _process_current_item(state, history, db)

        state["stage"] = STAGE_WAITING_CATEGORY
        return StandardResponse(
            status="success",
            tool="selecionar_categoria",
            message=f"Nenhum resultado em '{selected_category}'. Tentativa {attempts}/3 — tente outra categoria para '{item_name}':",
            data=[{"name": c} for c in CATEGORIES],
            context={"history": history, "state": state},
        )

    state["category_attempts"] = 0
    state["selected_category"] = ""
    state["stage"] = STAGE_WAITING_SERVICE
    prefix = f"{skip_message}\n\n" if skip_message else ""
    return StandardResponse(
        status="success",
        tool="buscar_servico",
        message=f"{prefix}Encontrei {len(services)} serviço(s) para '{item_name}'. Selecione:",
        data=services,
        context={"history": history, "state": state},
    )


def _ask_next(state: dict, history: list) -> StandardResponse:
    pending = state.get("pending_items", [])
    
    if not pending:
        selected = state.get("selected_items", [])
        return StandardResponse(
            status="success",
            tool="lista_completa",
            message=f"✅ Lista finalizada com {len(selected)} item(ns).",
            data=selected,
            context={"history": history, "state": state},
        )

    next_item = pending[0]
    state["stage"] = STAGE_WAITING_NEXT
    

    return StandardResponse(
        status="success",
        tool="proximo_item",
        message=f"Item concluído! Próximo: '{next_item['name']}'. Deseja continuar?",
        data=[{"name": "Sim, continuar"}, {"name": "Não, finalizar"}],
        context={"history": history, "state": state},
    )


def chat(text: str, context: dict[str, Any] | None, db) -> StandardResponse:
    context = context or {}
    history: list[dict] = context.get("history", [])
    state: dict[str, Any] = context.get("state", {
        "selected_items": [],
        "pending_items": [],
        "pending_supplies": [],
        "last_services": [],
        "last_products": [],
        "current_service": "",
        "current_supply": "",
        "selected_category": "",
        "stage": STAGE_IDLE,
        "total_items": 0,
    })

    stage = state.get("stage", STAGE_IDLE)


    if stage == STAGE_WAITING_NEXT:
        if "sim" in text.lower() or text.strip() == "1":
            state["stage"] = STAGE_IDLE
            return _process_current_item(state, history, db)
        else:
            selected = state.get("selected_items", [])
            return StandardResponse(
                status="success",
                tool="lista_completa",
                message=f"✅ Lista finalizada com {len(selected)} item(ns).",
                data=selected,
                context={"history": history, "state": state},
            )

    if text.startswith("confirm_category:"):
        category = text.replace("confirm_category:", "").strip()
        state["selected_category"] = category
        state["stage"] = STAGE_IDLE
        return _process_current_item(state, history, db)

    if stage == STAGE_WAITING_SERVICE and text.strip().isdigit():
        idx = int(text.strip()) - 1
        services = state.get("last_services", [])

        if 0 <= idx < len(services):
            chosen = services[idx]
            state["selected_items"].append({
                "description": chosen["description"],
                "type": "service",
                "status": "confirmado",
                "parent_service": None,
            })
            state["current_service"] = chosen["description"]
            state["pending_supplies"] = list(chosen.get("supplies", []))
            pending = state.get("pending_items", [])
            state["pending_items"] = pending[1:] if pending else []
            state["stage"] = STAGE_IDLE
        return _process_current_item(state, history, db)

    if stage == STAGE_WAITING_SUPPLY and text.strip().isdigit():
        idx = int(text.strip()) - 1
        products = state.get("last_products", [])

        if 0 <= idx < len(products):
            chosen = products[idx]
            state["selected_items"].append({
                "description": chosen["description"],
                "type": "product",
                "status": "confirmado",
                "parent_service": state.get("current_service", ""),
                "unity": chosen.get("unity", ""),
                "brand": chosen.get("brand", ""),
                "code": chosen.get("code", ""),
            })

        pending_supplies = state.get("pending_supplies", [])
        state["pending_supplies"] = pending_supplies[1:] if pending_supplies else []
        state["stage"] = STAGE_IDLE

        if state["pending_supplies"]:
            return _process_current_item(state, history, db)

        return _ask_next(state, history)

    if stage == STAGE_WAITING_PRODUCT and text.strip().isdigit():
        idx = int(text.strip()) - 1
        products = state.get("last_products", [])

        if 0 <= idx < len(products):
            chosen = products[idx]
            state["selected_items"].append({
                "description": chosen["description"],
                "type": "product",
                "status": "confirmado",
                "parent_service": None,
                "unity": chosen.get("unity", ""),
                "brand": chosen.get("brand", ""),
                "code": chosen.get("code", ""),
            })

        pending = state.get("pending_items", [])
        state["pending_items"] = pending[1:] if pending else []
        state["stage"] = STAGE_IDLE

        return _ask_next(state, history)
    
    items = _classify_items(text)
    state["pending_items"] = items
    state["total_items"] = len(items)
    state["selected_items"] = []
    state["pending_supplies"] = []
    state["current_service"] = ""
    state["current_supply"] = ""
    state["selected_category"] = ""
    state["stage"] = STAGE_IDLE

    return _process_current_item(state, history, db)