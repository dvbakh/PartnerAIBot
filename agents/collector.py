import json
import logging
import re

from openai import OpenAI

from config import MISTRAL_API_KEY
from storage.budget_repository import BudgetRepository

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=MISTRAL_API_KEY,
    base_url="https://api.mistral.ai/v1"
)

MODEL = "mistral-small-latest"

EXTRACT_PROMPT = """
Ты получаешь сообщение от менеджера со списком партнёров и бюджетов.
Извлеки эту информацию и верни **только JSON-массив** объектов с полями "partner" и "budget".
Пример ответа:
[
  {"partner": "Google", "budget": 1000},
  {"partner": "Meta", "budget": 2500}
]
Никаких лишних слов, только JSON-массив.
"""

class CollectorAgent:

    @staticmethod
    def extract_budgets(text: str):
        prompt = EXTRACT_PROMPT + "\n\nСообщение:\n" + text
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"}  # Mistral поддерживает это
            )
            raw = response.choices[0].message.content.strip()
        except Exception as e:
            logger.exception("Mistral API error")
            return []

        if not raw:
            logger.warning("Empty response from Mistral")
            return []

        # 1. Прямой парсинг
        try:
            data = json.loads(raw)
            # Иногда Mistral оборачивает массив в объект с ключом "budgets"
            if isinstance(data, dict) and "budgets" in data:
                return data["budgets"]
            if isinstance(data, list):
                return data
            # Если пришёл объект с одним элементом – обернём в список
            if isinstance(data, dict) and "partner" in data:
                return [data]
        except json.JSONDecodeError:
            pass

        # 2. Ищем JSON-массив в тексте
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

        logger.error(f"Cannot parse collector response: {raw[:200]}")
        return []

    @staticmethod
    def save_records(
        task_id: int,
        geo: str,
        channel: str,
        records: list
    ):
        for record in records:
            BudgetRepository.create(
                task_id=task_id,
                geo=geo,
                channel=channel,
                partner=record["partner"],
                budget=float(record["budget"])
            )