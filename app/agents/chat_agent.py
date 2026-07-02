import json
import logging
import os
import re
from typing import Any

from groq import Groq
from dotenv import load_dotenv

from app.schemas.responses import StandardResponse
from app.tools.definitions import TOOLS
from app.tools.executor import execute_tool

load_dotenv()

logger = logging.getLogger(__name__)

INTERACTIVE_TOOLS = {"buscar_servico", "buscar_produto", "lista_completa"}

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
_model = os.getenv("GROQ_MODEL", "llama3-8b-8192")


def _build_system_prompt(state: dict) -> str:
    pending = state.get("pending_items", [])
    selected_count = len(state.get("selected_items", []))
    total = state.get("total_items", 0)
    pending_supplies = state.get("pending_supplies", [])
    current_service = state.get("current_service", "")

    progress = ""
    if total > 0:
        progress = f"""
## CURRENT PROGRESS
- Total: {total} | Done: {selected_count} | Pending: {len(pending)}
- Pending items: {json.dumps(pending, ensure_ascii=False)}
"""

    supplies_progress = ""
    if pending_supplies:
        supplies_progress = f"""
## NEXT SUPPLY TO PROCESS (service: "{current_service}")
Search products for: "{pending_supplies[0]}"
Remaining after this: {len(pending_supplies) - 1} more supplies.
"""

    return f"""You are a technical assistant for construction works in Brazil.

## FLOW
1. New list → call set_item_list with ALL items
2. For each item:
   - SERVICE → search_services → engineer picks → confirm_selection → search products for each supply
   - MATERIAL → search_products → engineer picks → confirm_selection
3. All done → finish_list
{progress}{supplies_progress}
## RULES
- ONE tool at a time, no text with tool calls
- Number from engineer = selection from previous list
- finish_list only when pending items AND pending supplies are EMPTY

## QUERY TIPS
- Extract 2-3 essential words from the item description
- Remove accents, articles, prepositions
- Keep the most specific nouns
- If query returns no results, try different keywords from the same item
"""


def _call_groq(history: list, system_prompt: str) -> tuple:
    try:
        response = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
            ],
            tools=TOOLS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )
        return response, None
    except Exception as e:
        error_str = str(e)
        # Tenta recuperar do failed_generation
        if "failed_generation" in error_str:
            name_match = re.search(r'<function=([a-z_]+)', error_str)
            json_match = re.search(r'\{.*\}', error_str, re.DOTALL)
            if name_match:
                tool_name = name_match.group(1)
                try:
                    tool_args = json.loads(json_match.group(0)) if json_match else {}
                except Exception:
                    tool_args = {}

                class FakeFunction:
                    name = tool_name
                    arguments = json.dumps(tool_args)

                class FakeToolCall:
                    function = FakeFunction()

                class FakeMessage:
                    tool_calls = [FakeToolCall()]
                    content = ""

                class FakeChoice:
                    message = FakeMessage()

                class FakeResponse:
                    choices = [FakeChoice()]

                logger.info(f"Recuperado failed_generation: {tool_name} | {tool_args}")
                return FakeResponse(), None
        return None, e


def _parse_response(response) -> tuple:
    message = response.choices[0].message
    if message.tool_calls:
        tc = message.tool_calls[0]
        try:
            tool_args = json.loads(tc.function.arguments)
        except Exception:
            tool_args = {}
        return tc.function.name, tool_args, None
    return None, None, message.content or ""


def clean_history(history: list) -> list:
    valid_tool_ids = set()
    cleaned = []
    for msg in history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            valid_tool_ids.update(tc["id"] for tc in msg["tool_calls"])
            cleaned.append(msg)
        elif msg.get("role") == "tool":
            if msg.get("tool_call_id") in valid_tool_ids:
                cleaned.append(msg)
        else:
            cleaned.append(msg)
    return cleaned


def truncate_history(history: list, max_messages: int = 12) -> list:
    if len(history) <= max_messages:
        return history
    truncated = history[-max_messages:]
    while truncated and truncated[0].get("role") == "tool":
        truncated = truncated[1:]
    while truncated and truncated[0].get("role") == "assistant" and truncated[0].get("tool_calls"):
        truncated = truncated[1:]
    return truncated


def _append_tool_result(history: list, tool_call_id: str, tool_name: str, result: dict):
    history.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": result.get("_history_content") or json.dumps(
            {"found": result.get("found", 0), "status": result.get("tool", "ok")},
            ensure_ascii=False,
        ),
    })


def chat(text: str, context: dict[str, Any] | None, db) -> StandardResponse:
    context = context or {}
    history: list[dict] = context.get("history", [])
    state: dict[str, Any] = context.get("state", {"selected_items": []})

    if text:
        history.append({"role": "user", "content": text})

    history = clean_history(history)

    for iteration in range(10):
        logger.debug(f"Iteração {iteration + 1}/10")

        system_prompt = _build_system_prompt(state)
        response, error = _call_groq(truncate_history(history), system_prompt)

        if error:
            logger.error(f"Erro Groq: {error}")
            return StandardResponse(
                status="error",
                tool="erro",
                message=f"Erro ao processar: {str(error)}",
                data=[],
                context={"history": history, "state": state},
            )

        tool_name, tool_args, reply_text = _parse_response(response)

        if tool_name:
            fake_id = f"call_{iteration}"
            history.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": fake_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }],
            })

            logger.info(f"Tool: {tool_name} | Args: {tool_args}")
            result = execute_tool(tool_name, tool_args, db, state)
            print(">>> Tool executada:", tool_name)
            print(">>> tool_args:", tool_args)
            print(">>> last_services:", [s["description"][:50] for s in state.get("last_services", [])])
            print(">>> pending_supplies:", state.get("pending_supplies", []))
            print(">>> result tool:", result.get("tool"))
            _append_tool_result(history, fake_id, tool_name, result)

            if result.get("tool") in INTERACTIVE_TOOLS:
                return StandardResponse(
                    status="success",
                    tool=result["tool"],
                    message=result.get("message", ""),
                    data=result.get("data", []),
                    context={"history": history, "state": state},
                )

        elif reply_text:
            history.append({"role": "assistant", "content": reply_text})
            return StandardResponse(
                status="success",
                tool="mensagem",
                message=reply_text,
                data=[],
                context={"history": history, "state": state},
            )

        else:
            logger.warning(f"Resposta vazia na iteração {iteration + 1}")
            continue

    logger.warning("Limite de iterações atingido")
    return StandardResponse(
        status="error",
        tool="erro",
        message="Limite de processamento atingido. Envie uma nova mensagem para retomar.",
        data=[],
        context={"history": history, "state": state},
    )