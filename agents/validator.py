"""
Validator agent.

Receives the budgets submitted by a collector (REQUEST) and compares them with
last month's history. If a value deviates too much (or the partner is new), the
validator does NOT agree with the collector and disputes the data (CHALLENGE);
otherwise it confirms (INFORM). The conflict is resolved by the human: the
collector asks the manager to confirm.

This gives genuine cooperation with a possible disagreement between agents —
a feature of a multi-agent system rather than a plain pipeline.
"""

import logging
from typing import List

from agents.base import BaseAgent
from config import ANOMALY_THRESHOLD
from core.messages import AgentMessage, Performative
from storage.repositories import HistoryRepository

logger = logging.getLogger(__name__)


class ValidatorAgent(BaseAgent):
    def __init__(self, bus, notify=None):
        super().__init__("validator", bus, notify)

    async def receive(self, message: AgentMessage) -> None:
        if message.performative != Performative.REQUEST:
            return
        c = message.content
        issues = self._check(c["geo"], c["channel"], c["records"])

        if issues:
            await self.send(AgentMessage(
                performative=Performative.CHALLENGE,
                sender=self.name,
                receiver=message.sender,
                content={"collector_id": c["collector_id"], "issues": issues},
                conversation_id=message.conversation_id,
            ))
        else:
            await self.send(AgentMessage(
                performative=Performative.INFORM,
                sender=self.name,
                receiver=message.sender,
                content={"collector_id": c["collector_id"], "ok": True},
                conversation_id=message.conversation_id,
            ))

    def _check(self, geo: str, channel: str, records: List[dict]) -> List[dict]:
        """Return the list of suspicious items (empty = everything looks fine)."""
        issues = []
        for r in records:
            partner, budget = r["partner"], float(r["budget"])
            prev = HistoryRepository.get(geo, channel, partner)
            if prev is None or prev == 0:
                # a new partner is not an anomaly; nothing to compare against
                continue
            ratio = abs(budget - prev) / prev
            if ratio > ANOMALY_THRESHOLD:
                issues.append({
                    "partner": partner, "new": budget, "old": prev,
                    "change_pct": round(ratio * 100),
                })
        return issues
