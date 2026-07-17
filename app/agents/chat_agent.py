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
STAGE_WAITING_SERVICE_QUANTITY = "waiting_service_quantity"
STAGE_WAITING_SUPPLY = "waiting_supply"
STAGE_WAITING_PRODUCT = "waiting_product"
STAGE_WAITING_QUANTITY = "waiting_quantity"
STAGE_WAITING_NEXT = "waiting_next"
STAGE_WAITING_MANUAL_SEARCH = "waiting_manual_search"


def _classify_items(text: str) -> list[dict]:
    try:
        response = _client.chat.completions.create(
            model=_model,
            messages=[{
                "role": "user",
                "content": (
                    "Analise esta lista de itens de obra e classifique cada um.\n"
                    "IGNORE quantidades e unidades (100m, duas, 3 unidades, etc) — foque no ITEM.\n"
                    "SERVIÇO = ação a executar (instalar, assentar, pintar, demolir, executar, etc)\n"
                    "PRODUTO = material ou ferramenta (tinta, cabo, lixa, luminária, tomada, eletroduto, etc)\n\n"
                    "EXEMPLOS:\n"
                    "- 'duas tomadas' → product (name: 'tomada')\n"
                    "- '100m de eletroduto' → product (name: 'eletroduto')\n"
                    "- 'duas luminárias' → product (name: 'luminária')\n"
                    "- 'instalação de tomada' → service (name: 'instalação de tomada')\n\n"
                    f"Lista: {text}\n\n"
                    "Retorne APENAS JSON sem markdown:\n"
                    "{\"items\": [{\"name\": \"nome sem quantidade\", \"type\": \"service ou product\"}]}"
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
    words = text.strip().split()
    if len(words) <= 2:
        return text
    try:
        response = _client.chat.completions.create(
            model=_model,
            messages=[{
                "role": "user",
                "content": (
                    f"Extraia as palavras-chave do item para buscar em catálogo de obras. "
                    f"REMOVA quantidades, números, unidades de medida (m, cm, kg, un, etc). "
                    f"Use APENAS palavras que estão no item original. "
                    f"Retorne APENAS as palavras-chave essenciais, sem explicação.\n"
                    f"Item: '{text}'"
                )
            }],
            temperature=0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().lower()
        return result
    except Exception:
        return text


def _process_current_item(state: dict, history: list, db) -> StandardResponse:
    skip_message = state.pop("skip_message", None)
    pending_items = state.get("pending_items", [])
    pending_supplies = state.get("pending_supplies", [])

    def with_prefix(msg: str) -> str:
        return f"{skip_message}\n\n{msg}" if skip_message else msg

    # ── Insumos pendentes da composição ──────────────────────────────────────
    if pending_supplies:
        supply = pending_supplies[0]
        query = _make_query(supply)
        products = _search_products(query, db)
        state["last_products"] = products
        state["current_supply"] = supply
        state["manual_search_type"] = "product"
        state["manual_search_prev_stage"] = STAGE_WAITING_SUPPLY

        if not products:
            state["pending_supplies"] = pending_supplies[1:]
            if state["pending_supplies"]:
                return _process_current_item(state, history, db)
            else:
                state["stage"] = STAGE_WAITING_NEXT
                return _ask_next(state, history)

        state["stage"] = STAGE_WAITING_SUPPLY
        return StandardResponse(
            status="success",
            tool="buscar_produto",
            message=with_prefix(f"Insumo: '{supply}'. Selecione o produto:"),
            data=products,
            context={"history": history, "state": state},
        )

    # ── Sem itens → finaliza ──────────────────────────────────────────────────
    if not pending_items:
        selected = state.get("selected_items", [])
        return StandardResponse(
            status="success",
            tool="lista_completa",
            message=with_prefix(f"✅ Lista finalizada com {len(selected)} item(ns)."),
            data=selected,
            context={"history": history, "state": state},
        )

    item = pending_items[0]
    item_type = item.get("type", "service")
    item_name = item.get("name", "")

    # ── PRODUTO direto ────────────────────────────────────────────────────────
    if item_type == "product":
        query = _make_query(item_name)
        products = _search_products(query, db)
        state["last_products"] = products
        state["current_supply"] = ""
        state["manual_search_type"] = "product"
        state["manual_search_prev_stage"] = STAGE_WAITING_PRODUCT

        if not products:
            state["pending_items"] = pending_items[1:]
            return _process_current_item(state, history, db)

        state["stage"] = STAGE_WAITING_PRODUCT
        return StandardResponse(
            status="success",
            tool="buscar_produto",
            message=with_prefix(f"Encontrei produtos para '{item_name}'. Selecione:"),
            data=products,
            context={"history": history, "state": state},
        )

    # ── SERVIÇO: pede categoria primeiro ─────────────────────────────────────
    selected_category = state.get("selected_category", "")

    if not selected_category:
        state["stage"] = STAGE_WAITING_CATEGORY
        state["category_attempts"] = state.get("category_attempts", 0)
        return StandardResponse(
            status="success",
            tool="selecionar_categoria",
            message=with_prefix(f"Qual é a categoria do serviço '{item_name}'?"),
            data=[{"name": c} for c in CATEGORIES],
            context={"history": history, "state": state},
        )

    # ── SERVIÇO com categoria: busca serviços ─────────────────────────────────
    query = _make_query(item_name)
    services = _search_services(query, db, category=selected_category)
    state["last_services"] = services
    state["manual_search_type"] = "service"
    state["manual_search_prev_stage"] = STAGE_WAITING_SERVICE

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
            message=with_prefix(f"Nenhum resultado em '{selected_category}'. Tentativa {attempts}/3 — tente outra categoria para '{item_name}':"),
            data=[{"name": c} for c in CATEGORIES],
            context={"history": history, "state": state},
        )

    state["category_attempts"] = 0
    state["selected_category"] = ""
    state["stage"] = STAGE_WAITING_SERVICE
    return StandardResponse(
        status="success",
        tool="buscar_servico",
        message=with_prefix(f"Encontrei {len(services)} serviço(s) para '{item_name}'. Selecione:"),
        data=services,
        context={"history": history, "state": state},
    )


def _ask_next(state: dict, history: list) -> StandardResponse:
    pending = state.get("pending_items", [])
    state["stage"] = STAGE_WAITING_NEXT

    if not pending:
        selected = state.get("selected_items", [])
        return StandardResponse(
            status="success",
            tool="proximo_item",
            message=f"Item adicionado! Deseja adicionar mais itens ou finalizar?",
            data=[{"name": "Adicionar mais itens"}, {"name": "Finalizar lista"}],
            context={"history": history, "state": state},
        )

    next_item = pending[0]
    return StandardResponse(
        status="success",
        tool="proximo_item",
        message=f"Item concluído! Próximo: '{next_item['name']}'. Deseja continuar?",
        data=[{"name": "Sim, continuar"}, {"name": "Não, finalizar"}],
        context={"history": history, "state": state},
    )


def _ask_quantity(state: dict, history: list, product: dict) -> StandardResponse:
    state["pending_product"] = product
    state["stage"] = STAGE_WAITING_QUANTITY
    unity = product.get("unity", "") or ""
    return StandardResponse(
        status="success",
        tool="perguntar_quantidade",
        message=f"Qual a quantidade de '{product['description']}'?",
        data=[{"unity": unity}],
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
        "category_attempts": 0,
        "pending_product": None,
        "pending_service": None,
        "manual_search_type": "product",
        "manual_search_prev_stage": STAGE_WAITING_PRODUCT,
    })

    stage = state.get("stage", STAGE_IDLE)

    # ── Busca manual ──────────────────────────────────────────────────────────
    if text.startswith("manual_search:"):
        query = text.replace("manual_search:", "").strip()
        manual_type = state.get("manual_search_type", "product")
        prev_stage = state.get("manual_search_prev_stage", STAGE_WAITING_PRODUCT)

        if manual_type == "product":
            products = _search_products(query, db)
            state["last_products"] = products

            if not products:
                return StandardResponse(
                    status="success",
                    tool="buscar_manual",
                    message=f"Nenhum resultado para '{query}'. Tente outro termo:",
                    data=[],
                    context={"history": history, "state": state},
                )

            state["stage"] = prev_stage
            return StandardResponse(
                status="success",
                tool="buscar_produto",
                message=f"Encontrei {len(products)} produto(s) para '{query}'. Selecione:",
                data=products,
                context={"history": history, "state": state},
            )

        else:
            services = _search_services(query, db, category=state.get("selected_category", ""))
            state["last_services"] = services

            if not services:
                return StandardResponse(
                    status="success",
                    tool="buscar_manual",
                    message=f"Nenhum resultado para '{query}'. Tente outro termo:",
                    data=[],
                    context={"history": history, "state": state},
                )

            state["stage"] = STAGE_WAITING_SERVICE
            return StandardResponse(
                status="success",
                tool="buscar_servico",
                message=f"Encontrei {len(services)} serviço(s) para '{query}'. Selecione:",
                data=services,
                context={"history": history, "state": state},
            )

    # ── Próximo item ──────────────────────────────────────────────────────────
    if stage == STAGE_WAITING_NEXT:
        if "sim" in text.lower() or text.strip() == "1" or "adicionar" in text.lower():
            state["stage"] = STAGE_IDLE
            if not state.get("pending_items"):
                return StandardResponse(
                    status="success",
                    tool="mensagem",
                    message="Digite os itens que deseja adicionar à lista:",
                    data=[],
                    context={"history": history, "state": state},
                )
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

    # ── Quantidade digitada ───────────────────────────────────────────────────
    if stage == STAGE_WAITING_QUANTITY:
        quantity = text.strip() or "1"
        product = state.get("pending_product", {})
        is_supply = bool(state.get("pending_supplies")) and not state.get("pending_product_is_service")
        is_service = state.get("pending_product_is_service", False)

        if is_service:
            chosen = state.get("pending_service", {})
            item = {
                "description": chosen["description"],
                "type": "service",
                "status": "confirmado",
                "parent_service": None,
                "quantity": quantity,
                "unity": "UN",
            }
            state["selected_items"].append(item)
            state["current_service"] = chosen["description"]
            state["pending_supplies"] = list(chosen.get("supplies", []))
            pending = state.get("pending_items", [])
            state["pending_items"] = pending[1:] if pending else []
            state["pending_product"] = None
            state["pending_service"] = None
            state["pending_product_is_service"] = False
            state["stage"] = STAGE_IDLE


            if not state["pending_supplies"]:
                return _ask_next(state, history)
    

            return _process_current_item(state, history, db)


        item = {
            "description": product.get("description", ""),
            "type": "product",
            "status": "confirmado",
            "parent_service": state.get("current_service", "") if is_supply else None,
            "unity": product.get("unity", ""),
            "brand": product.get("brand", ""),
            "code": product.get("code", ""),
            "quantity": quantity,
        }
        state["selected_items"].append(item)
        state["pending_product"] = None
        state["pending_product_is_service"] = False

        if is_supply:
            pending_supplies = state.get("pending_supplies", [])
            state["pending_supplies"] = pending_supplies[1:] if pending_supplies else []
            state["stage"] = STAGE_IDLE
            if state["pending_supplies"]:
                return _process_current_item(state, history, db)
            return _ask_next(state, history)
        else:
            pending = state.get("pending_items", [])
            state["pending_items"] = pending[1:] if pending else []
            state["stage"] = STAGE_IDLE
            return _ask_next(state, history)

    # ── Categoria selecionada ─────────────────────────────────────────────────
    if text.startswith("confirm_category:"):
        category = text.replace("confirm_category:", "").strip()
        state["selected_category"] = category
        state["stage"] = STAGE_IDLE
        return _process_current_item(state, history, db)

    # ── Seleção de serviço → pede quantidade ─────────────────────────────────
    if stage == STAGE_WAITING_SERVICE and text.strip().isdigit():
        idx = int(text.strip()) - 1
        services = state.get("last_services", [])

        if 0 <= idx < len(services):
            chosen = services[idx]
            state["pending_service"] = chosen
            state["pending_product_is_service"] = True
            state["pending_product"] = {
                "description": chosen["description"],
                "unity": "UN",
            }
            state["stage"] = STAGE_WAITING_QUANTITY
            return StandardResponse(
                status="success",
                tool="perguntar_quantidade",
                message=f"Qual a quantidade do serviço '{chosen['description']}'?",
                data=[{"unity": "UN"}],
                context={"history": history, "state": state},
            )

        return _process_current_item(state, history, db)

    # ── Seleção de produto de insumo ──────────────────────────────────────────
    if stage == STAGE_WAITING_SUPPLY and text.strip().isdigit():
        idx = int(text.strip()) - 1
        products = state.get("last_products", [])

        if 0 <= idx < len(products):
            chosen = products[idx]
            return _ask_quantity(state, history, chosen)

        return _process_current_item(state, history, db)

    # ── Seleção de produto direto ─────────────────────────────────────────────
    if stage == STAGE_WAITING_PRODUCT and text.strip().isdigit():
        idx = int(text.strip()) - 1
        products = state.get("last_products", [])

        if 0 <= idx < len(products):
            chosen = products[idx]
            return _ask_quantity(state, history, chosen)

        return _process_current_item(state, history, db)

    # ── Nova lista ou adição de itens ─────────────────────────────────────────
    items = _classify_items(text)
    state["pending_items"] = items
    state["total_items"] = len(items)
    state["pending_supplies"] = []
    state["current_service"] = ""
    state["current_supply"] = ""
    state["selected_category"] = ""
    state["stage"] = STAGE_IDLE
    state["category_attempts"] = 0
    state["pending_product"] = None
    state["pending_service"] = None
    state["pending_product_is_service"] = False

    return _process_current_item(state, history, db)