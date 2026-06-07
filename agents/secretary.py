import json
import logging

from openai import OpenAI
from config import MISTRAL_API_KEY

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=MISTRAL_API_KEY,
    base_url="https://api.mistral.ai/v1"
)
MODEL = "mistral-small-latest"

class SecretaryAgent:
    """
    AI-агент для обработки сообщений менеджера.
    Извлекает месяц, список GEO и дедлайн с помощью Mistral.
    """

    def __init__(self):
        self.state = {
            "month": None,
            "geo_list": None,
            "deadline": None,
            "waiting_confirmation": False,
        }

    # ============================================================
    # Статический интерфейс для main.py
    # ============================================================
    @staticmethod
    def create_state() -> dict:
        """Создаёт начальное состояние (словарь)."""
        return {
            "month": None,
            "geo_list": None,
            "deadline": None,
            "waiting_confirmation": False,
        }

    @staticmethod
    def process_message(state: dict, text: str) -> dict:
        """
        Обрабатывает сообщение менеджера.
        Возвращает словарь с action, state и message.
        """
        agent = SecretaryAgent()
        agent.state = state

        # Извлекаем параметры через LLM
        extracted = agent._llm_extract_task(text)
        if extracted:
            agent._merge_state(extracted)

        if agent._is_state_complete():
            return {
                "action": "create_task",
                "state": agent.state,
                "message": "Задача сформирована. Запускаю сбор бюджета."
            }
        else:
            return {
                "action": "continue",
                "state": agent.state,
                "message": agent._build_missing_fields_message()
            }

    # ============================================================
    # LLM-экстракция параметров задачи
    # ============================================================
    def _llm_extract_task(self, user_message: str) -> dict:
        system_prompt = """
Ты — секретарь, который извлекает параметры задачи из сообщения менеджера.
Верни только JSON-объект с полями:
- month (строка, месяц, например "апрель")
- geo_list (массив строк, GEO из списка: KZ, BY, RU, UA, KG, AM, TJ, UZ)
- deadline (строка или null, если не указано)

Если какого-то поля нет, верни его как null.
Не добавляй никаких пояснений, только JSON.
"""
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)

            # Оставляем только допустимые GEO
            valid_geos = {"KZ", "BY", "RU"}
            if "geo_list" in data and isinstance(data["geo_list"], list):
                data["geo_list"] = [g.upper() for g in data["geo_list"] if g.upper() in valid_geos]
            return data
        except Exception as e:
            logger.exception("LLM extraction failed")
            return {}

    # ============================================================
    # Вспомогательные методы состояния
    # ============================================================
    def _merge_state(self, new_state: dict):
        for k in self.state:
            if k in new_state and new_state[k] is not None:
                self.state[k] = new_state[k]

    def _is_state_complete(self) -> bool:
        return all([
            self.state["month"],
            self.state["geo_list"],
            self.state["deadline"]
        ])

    def _build_missing_fields_message(self) -> str:
        missing = []
        if not self.state["month"]:
            missing.append("месяц")
        if not self.state["geo_list"]:
            missing.append("GEO")
        if not self.state["deadline"]:
            missing.append("дедлайн")
        return "Уточните: " + ", ".join(missing)