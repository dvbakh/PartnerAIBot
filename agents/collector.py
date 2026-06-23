"""
Collector agent (one per GEO×channel subtask).

Lifecycle:
  1) CANDIDATE  — takes part in the tender: on a CFP it submits a bid (PROPOSE)
                  based on the manager's reliability and current load.
  2) PRIMARY    — its bid was accepted (ACCEPT): it sends the request to the
                  manager and waits. It may send a reminder itself when a
                  deadline signal arrives — a piece of autonomous behaviour.
  3) checking   — once an answer arrives it parses the budgets and sends them to
                  the validator. If the validator disputes them (CHALLENGE) it
                  switches to a confirmation dialog with the manager
                  (AWAITING_CONFIRMATION).
  4) COMPLETED/FAILED/REJECTED — terminal states.

The agent notion (autonomy, reactivity) follows Wooldridge & Jennings (1995).
User-facing strings are kept in Russian.
"""

import logging
from typing import List, Optional

from agents.base import BaseAgent
from config import COLLECTOR_MAX_RETRIES
from core.messages import AgentMessage, Performative
from nlu.extractor import extract_budgets
from storage.repositories import (BudgetRepository, CollectorRepository,
                                  count_waiting_for_chat)

logger = logging.getLogger(__name__)

# affirmative / negative replies in the dispute dialog (Russian, user-facing input)
_YES = {"да", "да.", "ок", "ok", "верно", "подтверждаю", "yes", "confirm"}
_NO = {"нет", "нет.", "прошлое", "предыдущее", "замени", "заменить",
       "более вероятное", "no"}


class CollectorAgent(BaseAgent):
    def __init__(self, bus, notify, *, collector_id, task_id, geo, channel,
                 manager_name, manager_chat_id, month, deadline,
                 reliability=0.7):
        super().__init__(f"collector:{collector_id}", bus, notify)
        self.collector_id = collector_id
        self.task_id = task_id
        self.geo = geo
        self.channel = channel
        self.manager_name = manager_name
        self.manager_chat_id = manager_chat_id
        self.month = month
        self.deadline = deadline
        self.reliability = reliability
        self.status = "candidate"
        self.retries = 0
        self._records_in_flight: List[dict] = []
        self._suggested_records: List[dict] = []  # more-probable values for a dispute

    # ---------- reaction to messages from other agents ----------
    async def receive(self, message: AgentMessage) -> None:
        p = message.performative
        if p == Performative.CFP:
            await self._make_bid(message.content.get("round_id"))
        elif p == Performative.ACCEPT_PROPOSAL:
            await self._become_primary()
        elif p == Performative.REJECT_PROPOSAL:
            self.status = "rejected"  # stay as a backup
        elif p == Performative.INFORM:          # validator: data is fine
            await self._finalize(self._records_in_flight)
        elif p == Performative.CHALLENGE:        # validator: data looks suspicious
            await self._handle_challenge(message.content.get("issues", []))

    # ---------- tender ----------
    async def _make_bid(self, round_id) -> None:
        load = count_waiting_for_chat(self.manager_chat_id)
        bid = self.reliability * 100 - load * 5
        await self.send(AgentMessage(
            performative=Performative.PROPOSE,
            sender=self.name, receiver="coordinator",
            content={"collector_id": self.collector_id, "round_id": round_id,
                     "bid": bid, "name": self.manager_name},
            conversation_id=self.task_id,
        ))

    async def _become_primary(self) -> None:
        self.status = "primary"
        CollectorRepository.update_status(self.collector_id, "waiting_response")
        text = (
            f"Здравствуйте, {self.manager_name}.\n\n"
            f"Нужны бюджеты за {self.month}.\n"
            f"GEO: {self.geo}\nКанал: {self.channel}\nДедлайн: {self.deadline}\n\n"
            f"Пришлите список партнёров и сумм, например:\nGoogle 1000\nMeta 2500"
        )
        await self.notify_user(self.manager_chat_id, text)

    # ---------- reminder (on a deadline signal) ----------
    async def remind(self) -> None:
        if self.status == "primary":
            await self.notify_user(
                self.manager_chat_id,
                f"Напоминание: ждём бюджеты {self.geo}/{self.channel} "
                f"(дедлайн {self.deadline}).",
            )

    # ---------- manager's answer ----------
    async def handle_user(self, chat_id: int, text: str) -> Optional[str]:
        low = text.strip().lower()

        # continuation of the dialog after a dispute
        if self.status == "awaiting_confirmation":
            if low in _YES:                       # keep the submitted values
                await self._finalize(self._records_in_flight)
                return None
            if low in _NO:                        # assign the more probable values
                await self._finalize(self._suggested_records)
                return None
            # otherwise treat it as a corrected list — re-parse below

        records = extract_budgets(text)
        if not records:
            self.retries += 1
            if self.retries <= COLLECTOR_MAX_RETRIES:
                return ("Не удалось распознать бюджеты. По одной строке на партнёра, "
                        "например:\nGoogle 1000\nMeta 2500")
            CollectorRepository.update_status(self.collector_id, "failed")
            self.status = "failed"
            await self.send(AgentMessage(
                performative=Performative.REPORT, sender=self.name,
                receiver="coordinator",
                content={"collector_id": self.collector_id, "ok": False},
                conversation_id=self.task_id,
            ))
            return "Не получилось распознать данные. Подзадача закрыта без результата."

        # send the data to the validator; its verdict will arrive in receive()
        self._records_in_flight = records
        self.status = "validating"
        await self.send(AgentMessage(
            performative=Performative.REQUEST, sender=self.name,
            receiver="validator",
            content={"collector_id": self.collector_id, "geo": self.geo,
                     "channel": self.channel, "records": records},
            conversation_id=self.task_id,
        ))
        return None

    async def _handle_challenge(self, issues: List[dict]) -> None:
        self.status = "awaiting_confirmation"
        # the validator's "more probable" value for a partner is last month's value
        probable = {i["partner"]: i["old"] for i in issues}
        self._suggested_records = [
            {"partner": r["partner"], "budget": probable.get(r["partner"], r["budget"])}
            for r in self._records_in_flight
        ]
        lines = "\n".join(
            f"{i['partner']}: {i['new']:.0f} (в прошлом месяце {i['old']:.0f}, "
            f"изменение ~{i['change_pct']}%)" for i in issues
        )
        await self.notify_user(
            self.manager_chat_id,
            "Проверка нашла резкие отклонения от прошлого месяца:\n"
            f"{lines}\n\n"
            "«да» — оставить присланные суммы.\n"
            "«нет» — принять более вероятные значения прошлого месяца.\n"
            "Либо пришлите исправленный список.",
        )

    async def _finalize(self, records: List[dict]) -> None:
        for r in records:
            BudgetRepository.create(self.task_id, self.geo, self.channel,
                                    self.manager_name, r["partner"], float(r["budget"]))
        CollectorRepository.update_status(self.collector_id, "completed")
        self.status = "completed"
        lines = "\n".join(f"{r['partner']} — {float(r['budget']):.0f}" for r in records)
        await self.notify_user(
            self.manager_chat_id,
            f"Принято ({self.geo}/{self.channel}), спасибо.\n{lines}",
        )
        await self.send(AgentMessage(
            performative=Performative.REPORT, sender=self.name,
            receiver="coordinator",
            content={"collector_id": self.collector_id, "ok": True,
                     "count": len(records)},
            conversation_id=self.task_id,
        ))
