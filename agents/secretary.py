import sys
import os
import logging
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
import json
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

class SecretaryState(TypedDict):
    messages: List[dict]
    task_params: dict
    missing_fields: List[str]
    next_action: str

# ---------- Mistral API клиент ----------
client = OpenAI(
    api_key=MISTRAL_API_KEY,
    base_url="https://api.mistral.ai/v1"
)
MISTRAL_MODEL = "mistral-small-latest"   # или "open-mistral-7b" (бесплатный)

EXTRACT_PROMPT = """Ты — ассистент менеджера по сбору бюджетов.
Извлеки из сообщения параметры задачи:
- month (строка, например "май 2026")
- geo_list (список гео, например ["BY","KZ"])
- deadline (строка, например "2026-05-05 18:00")
Если какого-то параметра нет, оставь его значение пустым (null).
Ответь ТОЛЬКО JSON-объектом без пояснений.
Пример: {"month":"май 2026","geo_list":["BY","KZ"],"deadline":"2026-05-05 18:00"}"""

def call_mistral(prompt: str) -> str:
    """Запрос к Mistral API через OpenAI-совместимый интерфейс."""
    try:
        response = client.chat.completions.create(
            model=MISTRAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=256
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Mistral API call failed: {e}")
        return ""

def extract_params(state: SecretaryState) -> SecretaryState:
    user_msg = state["messages"][-1]["content"]
    full_prompt = EXTRACT_PROMPT + "\nСообщение менеджера: " + user_msg
    raw_response = call_mistral(full_prompt)

    # Mistral обычно не дублирует промпт, но на всякий случай очистим
    if full_prompt in raw_response:
        raw_response = raw_response.split(full_prompt)[-1].strip()

    try:
        extracted = json.loads(raw_response)
    except Exception:
        extracted = {}

    current_params = state.get("task_params", {})
    for key, value in extracted.items():
        if value:
            current_params[key] = value
    state["task_params"] = current_params
    return state

# -------- Остальные функции остаются БЕЗ ИЗМЕНЕНИЙ --------
def check_missing(state: SecretaryState) -> SecretaryState:
    required = ["month", "geo_list", "deadline"]
    missing = [f for f in required if not state["task_params"].get(f)]
    state["missing_fields"] = missing
    state["next_action"] = "ask" if missing else "confirm"
    return state

def generate_question(state: SecretaryState) -> SecretaryState:
    prompts = {
        "month": "За какой месяц нужно собрать бюджеты?",
        "geo_list": "По каким гео собираем? (например, BY, KZ)",
        "deadline": "Какой крайний срок сдачи бюджетов?"
    }
    questions = [prompts[m] for m in state["missing_fields"]]
    text = "Для запуска сбора нужно уточнить:\n" + "\n".join(f"- {q}" for q in questions)
    state["messages"].append({"role": "assistant", "content": text})
    return state

def confirm_task(state: SecretaryState) -> SecretaryState:
    params = state["task_params"]
    text = (
        f"Проверьте задачу:\n"
        f"Месяц: {params['month']}\n"
        f"Гео: {params['geo_list']}\n"
        f"Дедлайн: {params['deadline']}\n\n"
        f"Всё верно? Запускаем сбор?"
    )
    state["messages"].append({"role": "assistant", "content": text})
    state["next_action"] = "wait_confirmation"
    return state

def process_confirmation(state: SecretaryState) -> SecretaryState:
    user_msg = state["messages"][-1]["content"].lower()
    if any(word in user_msg for word in ["да", "запускай", "верно", "подтверждаю", "запустить", "ок"]):
        state["next_action"] = "complete"
        state["messages"].append({"role": "assistant", "content": "Принято. Запускаю сбор бюджетов."})
    else:
        state["next_action"] = "ask"
        state["messages"].append({"role": "assistant", "content": "Что нужно изменить?"})
    return state

def build_secretary_graph():
    graph = StateGraph(SecretaryState)
    graph.add_node("extract", extract_params)
    graph.add_node("check_missing", check_missing)
    graph.add_node("ask_question", generate_question)
    graph.add_node("confirm", confirm_task)
    graph.add_node("process_confirm", process_confirmation)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "check_missing")
    graph.add_conditional_edges(
        "check_missing",
        lambda s: "ask" if s["next_action"] == "ask" else "confirm",
        {"ask": "ask_question", "confirm": "confirm"}
    )
    graph.add_edge("ask_question", END)
    graph.add_edge("confirm", END)
    return graph.compile()

secretary_app = build_secretary_graph()

def run_secretary_turn(state: SecretaryState) -> SecretaryState:
    if state.get("next_action") == "wait_confirmation":
        state = process_confirmation(state)
        if state["next_action"] == "ask":
            state = extract_params(state)
            state = check_missing(state)
            if state["next_action"] == "ask":
                state = generate_question(state)
            else:
                state = confirm_task(state)
    else:
        state = secretary_app.invoke(state)
    return state