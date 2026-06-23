"""
Headless demonstration / self-check WITHOUT Telegram ("Path A").

Runs all the key mechanisms in the console:
  1) a tender for the executor (Contract Net): of two candidate managers for
     BY/Mobile the more reliable one wins;
  2) a missed deadline and reassignment to a backup (simulated by calling
     handle_timeout, just like the /timeout command would);
  3) the validator's check: a suspicious amount is disputed and the human
     confirms it;
  4) the normal path and the final report (sums by channel and by GEO, and how
     many partners each manager submitted).

Note: roles — the analyst states the task and gets the report; the managers
provide the budgets. The literal Russian phrases below are the user input fed
into the (Russian-language) bot, so they stay in Russian.

Run:  python simulate.py
"""

import asyncio

from core.bus import MessageBus
from agents.secretary import SecretaryAgent
from agents.coordinator import CoordinatorAgent
from agents.reporter import ReporterAgent
from agents.validator import ValidatorAgent
from storage.db import init_db, reset_db
from storage.repositories import CollectorRepository
from config import ANALYST_CHAT_ID


async def main():
    init_db()
    reset_db(seed_history=True)

    async def notify(chat_id, text, keyboard=None):
        print(f"[Bot -> {chat_id}]\n{text}\n")

    bus = MessageBus()
    secretary = SecretaryAgent(bus, notify)
    coordinator = CoordinatorAgent(bus, notify)
    ReporterAgent(bus, notify)
    ValidatorAgent(bus, notify)

    chat = ANALYST_CHAT_ID

    async def manager_reply(answer):
        active = CollectorRepository.get_active_by_chat_id(chat)
        if not active:
            print(">>> no active request\n")
            return
        print(f"[Manager {active['manager_name']} "
              f"({active['geo']}/{active['channel']})]: {answer!r}\n")
        agent = coordinator.get_collector_agent(active["id"])
        reply = await agent.handle_user(chat, answer)
        if reply:
            print(f"[Bot -> {chat}]\n{reply}\n")

    print("===== 1. Analyst states the task (the tender starts) =====\n")
    await secretary.handle_user(chat, "Собери бюджеты за апрель по BY, дедлайн 25.04")

    print("===== 2. Simulate a missed deadline for the first manager =====\n")
    active = CollectorRepository.get_active_by_chat_id(chat)
    await coordinator.handle_timeout(active["id"])

    print("===== 3. The backup manager answers (with an anomalous amount) =====\n")
    await manager_reply("Google 1000\nMeta 9000")

    print("===== 4. The human confirms the disputed amount =====\n")
    await manager_reply("да")

    print("===== 5. The second channel answers normally =====\n")
    await manager_reply("Yandex 3000")


if __name__ == "__main__":
    asyncio.run(main())
