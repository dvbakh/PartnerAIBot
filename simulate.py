"""
Headless demonstration / self-check WITHOUT Telegram ("Path A").

One GEO (BY) is used to keep the demo focused. It runs all the key mechanisms:
  1) a tender for the executor (Contract Net): of two candidate managers for
     BY/Mobile the more reliable one wins;
  2) a missed deadline and reassignment to a backup (handle_timeout, like the
     /timeout command);
  3) the validator's check: a suspicious amount is disputed; here the human
     answers "нет" and the system assigns the more probable (last month's) value;
  4) the normal path and the final report.

The literal Russian phrases below are the user input fed into the
(Russian-language) bot, so they stay in Russian.

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

    async def answer_as(collector_id, text):
        row = CollectorRepository.get(collector_id)
        print(f"[Manager {row['manager_name']} ({row['geo']}/{row['channel']})]: "
              f"{text!r}\n")
        agent = coordinator.get_collector_agent(collector_id)
        reply = await agent.handle_user(chat, text)
        if reply:
            print(f"[Bot -> {chat}]\n{reply}\n")

    print("===== 1. Analyst states the task; the tender starts (BY only) =====\n")
    await secretary.handle_user(chat, "Собери бюджеты за апрель по BY, дедлайн 25.04")

    print("===== 2. The first manager misses the deadline -> reassignment =====\n")
    primary = CollectorRepository.get_active_by_chat_id(chat)  # Марина (BY/Mobile)
    await coordinator.handle_timeout(primary["id"])

    print("===== 3. The backup answers with an anomalous amount =====\n")
    backup = CollectorRepository.get_active_by_chat_id(chat)    # Ольга (BY/Mobile)
    await answer_as(backup["id"], "Google 1000\nMeta 9000")

    print("===== 4. Human says 'нет' -> the more probable value is assigned =====\n")
    await answer_as(backup["id"], "нет")

    print("===== 5. The other channel answers normally =====\n")
    media = CollectorRepository.get_active_by_chat_id(chat)     # Екатерина (BY/Media)
    await answer_as(media["id"], "Yandex 3000")


if __name__ == "__main__":
    asyncio.run(main())
