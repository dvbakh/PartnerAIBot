"""
Coordinator agent.

On receiving a task from the secretary (REQUEST), for every GEO×channel subtask
it runs a small tender following the Contract Net Protocol (Smith, 1980):
  - announces the subtask to candidate managers (CFP);
  - collects their bids (PROPOSE), which depend on reliability and load;
  - awards it to the primary manager (ACCEPT), keeping the rest as backups (REJECT).

If the analyst named specific channels, only those channels are collected;
otherwise all channels of each GEO are collected.

Then it tracks progress: it accepts reports (REPORT) and, on a missed-deadline
signal, reassigns the subtask to a backup manager (handle_timeout). When all
subtasks are closed it asks the reporter to assemble the result.

The coordinator does not run asyncio timers itself: the runtime (the bot) tells
it when a deadline is due and receives on_assigned/on_resolved callbacks to set
and cancel timers. This keeps decision logic inside the agent.

User-facing strings are kept in Russian.
"""

import logging
from typing import Callable, Dict, List, Optional

from agents.base import BaseAgent
from agents.collector import CollectorAgent
from config import GEO_STRUCTURE
from core.messages import AgentMessage, Performative
from models.task import Task
from storage.repositories import CollectorRepository, TaskRepository

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    def __init__(self, bus, notify):
        super().__init__("coordinator", bus, notify)
        self._notify_fn = notify
        self._collectors: Dict[int, CollectorAgent] = {}
        self._proposals: Dict[str, List[dict]] = {}
        self._backups: Dict[str, List[int]] = {}
        self._round_of: Dict[int, str] = {}
        self._round_meta: Dict[str, dict] = {}
        self._resolved_rounds = set()
        self._pending: Dict[int, int] = {}
        self._analyst_chat: Dict[int, int] = {}
        # runtime callbacks (wired by the bot)
        self.on_assigned: Optional[Callable[[int], None]] = None
        self.on_resolved: Optional[Callable[[int], None]] = None

    async def receive(self, message: AgentMessage) -> None:
        p = message.performative
        if p == Performative.REQUEST:
            await self._handle_new_task(message.content)
        elif p == Performative.PROPOSE:
            self._collect_proposal(message.content)
        elif p == Performative.REPORT:
            await self._handle_report(message.content, message.conversation_id)

    # ================= new task: a tender per subtask =================
    async def _handle_new_task(self, content: dict) -> None:
        analyst_chat_id = content.get("analyst_chat_id")
        task = Task(month=content["month"], geo_list=content["geo_list"],
                    channels=content.get("channels", []),
                    deadline=content["deadline"], status="in_progress")
        task_id = TaskRepository.create(task)
        task.id = task_id
        self._analyst_chat[task_id] = analyst_chat_id

        subtasks = self._list_subtasks(task)
        if not subtasks:
            await self.notify_user(analyst_chat_id,
                                   "Не нашлось ответственных для выбранных GEO/каналов.")
            return

        self._pending[task_id] = len(subtasks)
        logger.info("Coordinator: task #%s, subtasks: %s", task_id, len(subtasks))

        for geo, channel, candidates in subtasks:
            await self._run_tender(task, geo, channel, candidates)

    def _list_subtasks(self, task: Task):
        """Expand the task into (geo, channel, candidates), honouring the
        optional channel filter."""
        wanted = set(task.channels or [])
        out = []
        for geo in task.geo_list:
            geo_info = GEO_STRUCTURE.get(geo)
            if not geo_info:
                continue
            for channel, candidates in geo_info["channels"].items():
                if wanted and channel not in wanted:
                    continue
                out.append((geo, channel, candidates))
        return out

    async def _run_tender(self, task: Task, geo: str, channel: str, candidates: list):
        round_id = f"{task.id}:{geo}:{channel}"
        self._round_meta[round_id] = {"task_id": task.id, "geo": geo, "channel": channel}
        self._proposals[round_id] = []

        # create a candidate agent for every possible manager
        for cand in candidates:
            collector_id = CollectorRepository.create(
                task_id=task.id, geo=geo, channel=channel,
                manager_name=cand["name"], manager_chat_id=cand["chat_id"],
                status="candidate",
            )
            agent = CollectorAgent(
                self.bus, self._notify_fn,
                collector_id=collector_id, task_id=task.id, geo=geo, channel=channel,
                manager_name=cand["name"], manager_chat_id=cand["chat_id"],
                month=task.month, deadline=task.deadline,
                reliability=cand.get("reliability", 0.7),
            )
            self._collectors[collector_id] = agent
            self._round_of[collector_id] = round_id
            # announce the subtask — the bid returns into _collect_proposal (reentrantly)
            await self.send(AgentMessage(
                performative=Performative.CFP, sender=self.name,
                receiver=agent.name, content={"round_id": round_id},
                conversation_id=task.id,
            ))

        await self._award(round_id)

    def _collect_proposal(self, content: dict) -> None:
        round_id = content["round_id"]
        self._proposals.setdefault(round_id, []).append(content)

    async def _award(self, round_id: str) -> None:
        proposals = sorted(self._proposals.get(round_id, []),
                           key=lambda x: x["bid"], reverse=True)
        if not proposals:
            return
        winner = proposals[0]["collector_id"]
        self._backups[round_id] = [p["collector_id"] for p in proposals[1:]]
        await self.send(AgentMessage(
            performative=Performative.ACCEPT_PROPOSAL, sender=self.name,
            receiver=f"collector:{winner}", conversation_id=None,
        ))
        for p in proposals[1:]:
            await self.send(AgentMessage(
                performative=Performative.REJECT_PROPOSAL, sender=self.name,
                receiver=f"collector:{p['collector_id']}",
            ))
        if self.on_assigned:
            self.on_assigned(winner)

    # ================= manager's report =================
    async def _handle_report(self, content: dict, task_id: int) -> None:
        collector_id = content["collector_id"]
        round_id = self._round_of.get(collector_id)
        if round_id is None or round_id in self._resolved_rounds:
            return
        self._resolve_round(round_id, task_id)
        if self.on_resolved:
            self.on_resolved(collector_id)
        await self._maybe_finish(task_id)

    def _resolve_round(self, round_id: str, task_id: int) -> None:
        self._resolved_rounds.add(round_id)
        self._pending[task_id] = self._pending.get(task_id, 1) - 1

    async def _maybe_finish(self, task_id: int) -> None:
        if self._pending.get(task_id, 0) <= 0:
            TaskRepository.update_status(task_id, "collected")
            await self.send(AgentMessage(
                performative=Performative.REQUEST, sender=self.name,
                receiver="reporter",
                content={"task_id": task_id,
                         "analyst_chat_id": self._analyst_chat.get(task_id)},
                conversation_id=task_id,
            ))

    # ================= deadline: reminder / escalation =================
    def is_waiting(self, collector_id: int) -> bool:
        row = CollectorRepository.get(collector_id)
        return bool(row and row["status"] == "waiting_response")

    async def remind(self, collector_id: int) -> None:
        agent = self._collectors.get(collector_id)
        if agent:
            await agent.remind()

    async def handle_timeout(self, collector_id: int) -> Optional[int]:
        """The primary manager did not answer: reassign to a backup."""
        round_id = self._round_of.get(collector_id)
        if round_id is None or round_id in self._resolved_rounds:
            return None
        if not self.is_waiting(collector_id):
            return None  # already answered

        meta = self._round_meta.get(round_id, {})
        task_id = meta.get("task_id")
        analyst_chat = self._analyst_chat.get(task_id)

        # close the silent one
        CollectorRepository.update_status(collector_id, "timed_out")
        old = self._collectors.get(collector_id)
        if old:
            old.status = "failed"
        if self.on_resolved:
            self.on_resolved(collector_id)

        backups = self._backups.get(round_id, [])
        if backups:
            next_id = backups.pop(0)
            await self.notify_user(
                analyst_chat,
                f"От менеджера «{old.manager_name if old else '—'}» нет ответа по "
                f"{meta.get('geo')}/{meta.get('channel')}. Переназначаю на резерв.",
            )
            await self.send(AgentMessage(
                performative=Performative.ACCEPT_PROPOSAL, sender=self.name,
                receiver=f"collector:{next_id}",
            ))
            if self.on_assigned:
                self.on_assigned(next_id)
            return next_id

        # no backups left — the subtask fails
        await self.notify_user(
            analyst_chat,
            f"По {meta.get('geo')}/{meta.get('channel')} никто не ответил, "
            f"данные не собраны.",
        )
        self._resolve_round(round_id, task_id)
        await self._maybe_finish(task_id)
        return None

    # ================= routing the manager's answer =================
    def get_collector_agent(self, collector_id: int) -> Optional[CollectorAgent]:
        agent = self._collectors.get(collector_id)
        if agent is not None:
            return agent
        row = CollectorRepository.get(collector_id)
        if not row:
            return None
        task = TaskRepository.get(row["task_id"])
        agent = CollectorAgent(
            self.bus, self._notify_fn,
            collector_id=row["id"], task_id=row["task_id"],
            geo=row["geo"], channel=row["channel"],
            manager_name=row["manager_name"] or "коллега",
            manager_chat_id=row["manager_chat_id"],
            month=task.month if task else "", deadline=task.deadline if task else "",
        )
        agent.status = "primary"
        self._collectors[collector_id] = agent
        self._pending.setdefault(row["task_id"], 1)
        self._analyst_chat.setdefault(row["task_id"], row["manager_chat_id"])
        self._round_of.setdefault(collector_id, f"{row['task_id']}:{row['geo']}:{row['channel']}")
        return agent
