"""
Secretary agent.

Talks to the analyst in natural language and collects the task parameters:
month, GEO list, optional channels and deadline. If a required field is missing
it asks again (mixed-initiative interaction, Horvitz 1999). Channels are
optional: if the analyst names a channel (e.g. "по BY Mobile"), only that
channel is collected; otherwise all channels of each GEO are collected.

Once the required fields are gathered the secretary forms the task and asks the
coordinator to carry it out (REQUEST performative).

User-facing strings are kept in Russian on purpose.
"""

import logging
from typing import Dict, Optional

from agents.base import BaseAgent
from core.messages import AgentMessage, Performative
from nlu.extractor import extract_task

logger = logging.getLogger(__name__)


class SecretaryAgent(BaseAgent):
    def __init__(self, bus, notify):
        super().__init__("secretary", bus, notify)
        self._states: Dict[int, dict] = {}  # per-chat dialog state

    @staticmethod
    def _empty_state() -> dict:
        return {"month": None, "geo_list": [], "channels": [], "deadline": None}

    def reset(self, chat_id: int) -> None:
        self._states.pop(chat_id, None)

    async def handle_user(self, chat_id: int, text: str) -> Optional[str]:
        """
        Handle an analyst's line. Returns the reply text to show, or None if the
        agent has already sent everything itself via notify.
        """
        state = self._states.get(chat_id) or self._empty_state()

        extracted = extract_task(text)
        if extracted.get("month"):
            state["month"] = extracted["month"]
        if extracted.get("geo_list"):
            for g in extracted["geo_list"]:
                if g not in state["geo_list"]:
                    state["geo_list"].append(g)
        if extracted.get("channels"):
            for c in extracted["channels"]:
                if c not in state["channels"]:
                    state["channels"].append(c)
        if extracted.get("deadline"):
            state["deadline"] = extracted["deadline"]

        self._states[chat_id] = state

        if self._is_complete(state):
            self.reset(chat_id)
            channels_text = ", ".join(state["channels"]) if state["channels"] else "все"
            # first confirm to the analyst (user-facing, Russian)
            await self.notify_user(
                chat_id,
                f"Задача сформирована:\n"
                f"• Месяц: {state['month']}\n"
                f"• GEO: {', '.join(state['geo_list'])}\n"
                f"• Каналы: {channels_text}\n"
                f"• Дедлайн: {state['deadline']}\n\n"
                f"Запускаю сбор бюджетов…",
            )
            # then ask the coordinator to execute it
            await self.send(AgentMessage(
                performative=Performative.REQUEST,
                sender=self.name,
                receiver="coordinator",
                content={**state, "analyst_chat_id": chat_id},
            ))
            return None

        return self._ask_missing(state)

    @staticmethod
    def _is_complete(state: dict) -> bool:
        # channels are optional; month, GEO and deadline are required
        return bool(state["month"] and state["geo_list"] and state["deadline"])

    @staticmethod
    def _ask_missing(state: dict) -> str:
        missing = []
        if not state["month"]:
            missing.append("месяц")
        if not state["geo_list"]:
            missing.append("GEO (BY, KZ, RU)")
        if not state["deadline"]:
            missing.append("дедлайн")
        return ("Чтобы запустить сбор, уточните: " + ", ".join(missing) +
                ".\n(Канал можно не указывать — тогда соберём по всем каналам.)")
