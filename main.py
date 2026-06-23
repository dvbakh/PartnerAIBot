"""
Entry point: the Telegram bot (a thin interface layer, HCI).

The bot translates the human's messages into agent calls and shows the replies.
It also acts as the "runtime": it arms the deadline timers and tells the
coordinator when it is time to remind or to reassign a subtask.

Roles:
  * Analyst (аналитик) — states the collection task and receives the report.
  * Manager (менеджер) — provides the budgets for a given channel.

Single-account demonstration: the role (analyst/manager) is switched with
buttons, so the whole cycle can be shown by one person. The /timeout command
immediately simulates a missed deadline — handy to show the reminder and the
reassignment without waiting for the real timer.

User-facing strings are kept in Russian.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from config import (ESCALATE_AFTER_SEC, PROXY_URL, REMINDER_AFTER_SEC,
                    TELEGRAM_TOKEN, USE_PROXY)
from core.bus import MessageBus
from agents.secretary import SecretaryAgent
from agents.coordinator import CoordinatorAgent
from agents.reporter import ReporterAgent
from agents.validator import ValidatorAgent
from storage.db import init_db, reset_db
from storage.repositories import CollectorRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BTN_ANALYST = "📊 Аналитик"
BTN_MANAGER = "👔 Менеджер"
ROLE_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_ANALYST), KeyboardButton(text=BTN_MANAGER)]],
    resize_keyboard=True,
)

roles: dict[int, str] = {}

session = AiohttpSession(proxy=PROXY_URL) if USE_PROXY else AiohttpSession()
bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()


async def notify(chat_id: int, text: str, keyboard=None) -> None:
    await bot.send_message(chat_id, text, reply_markup=keyboard)


# ---------- multi-agent system ----------
bus = MessageBus()
secretary = SecretaryAgent(bus, notify)
coordinator = CoordinatorAgent(bus, notify)
reporter = ReporterAgent(bus, notify)
validator = ValidatorAgent(bus, notify)


# ---------- deadline timers (the runtime for the agents) ----------
watch_tasks: dict[int, asyncio.Task] = {}


def schedule_watch(collector_id: int) -> None:
    cancel_watch(collector_id)
    watch_tasks[collector_id] = asyncio.create_task(_watch(collector_id))


def cancel_watch(collector_id: int) -> None:
    t = watch_tasks.pop(collector_id, None)
    if t and t is not asyncio.current_task():
        t.cancel()


async def _watch(collector_id: int) -> None:
    try:
        await asyncio.sleep(REMINDER_AFTER_SEC)
        if coordinator.is_waiting(collector_id):
            await coordinator.remind(collector_id)
        await asyncio.sleep(max(1, ESCALATE_AFTER_SEC - REMINDER_AFTER_SEC))
        if coordinator.is_waiting(collector_id):
            await coordinator.handle_timeout(collector_id)
    except asyncio.CancelledError:
        pass


coordinator.on_assigned = schedule_watch
coordinator.on_resolved = cancel_watch


# =========================================================
# Commands
# =========================================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    roles.pop(message.chat.id, None)
    await message.answer(
        "Привет! Прототип мультиагентного сбора бюджетов.\n\n"
        "Выберите роль кнопкой ниже:\n"
        "• Аналитик — поставить задачу на сбор и получить отчёт;\n"
        "• Менеджер — прислать бюджеты по запросу.\n\n"
        "Команды: /help, /reset, /status, /timeout.",
        reply_markup=ROLE_KB,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Сценарий демонстрации с одного аккаунта:\n"
        "1) «Аналитик» → напишите задачу, например:\n"
        "   «Собери бюджеты за апрель по BY, дедлайн 25.04».\n"
        "   Можно указать канал: «… по BY Mobile …» — тогда соберём только его.\n"
        "2) Бот проведёт тендер и пришлёт запросы менеджерам.\n"
        "3) «Менеджер» → отвечайте списком, например:\n"
        "   Google 1000\n   Meta 9000\n"
        "   (если сумма резко отличается от прошлого месяца, проверка переспросит).\n"
        "4) /timeout — сымитировать просрочку дедлайна и показать переназначение.\n"
        "5) Когда все подзадачи закрыты, аналитик получит итоговый отчёт.\n\n"
        "/reset — начать заново.",
        reply_markup=ROLE_KB,
    )


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    for cid in list(watch_tasks):
        cancel_watch(cid)
    reset_db(seed_history=True)
    roles.clear()
    secretary._states.clear()
    coordinator._collectors.clear()
    coordinator._proposals.clear()
    coordinator._backups.clear()
    coordinator._round_of.clear()
    coordinator._round_meta.clear()
    coordinator._resolved_rounds.clear()
    coordinator._pending.clear()
    coordinator._analyst_chat.clear()
    await message.answer("Данные очищены, история прошлого месяца восстановлена.",
                         reply_markup=ROLE_KB)


@dp.message(Command("status"))
async def cmd_status(message: Message):
    chat_id = message.chat.id
    role = roles.get(chat_id, "не выбрана")
    active = CollectorRepository.get_active_by_chat_id(chat_id)
    extra = (f"\nОжидает ответа: {active['geo']}/{active['channel']} "
             f"({active['manager_name']})." if active else "\nАктивных запросов нет.")
    await message.answer(f"Ваша роль: {role}.{extra}", reply_markup=ROLE_KB)


@dp.message(Command("timeout"))
async def cmd_timeout(message: Message):
    """Simulate a missed deadline for the current active request."""
    active = CollectorRepository.get_active_by_chat_id(message.chat.id)
    if not active:
        await message.answer("Нет активного запроса, который можно просрочить.",
                             reply_markup=ROLE_KB)
        return
    await coordinator.handle_timeout(active["id"])


# =========================================================
# Main handler
# =========================================================
@dp.message()
async def on_message(message: Message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    if not text:
        return

    if text == BTN_ANALYST:
        roles[chat_id] = "analyst"
        await message.answer("Роль: аналитик. Опишите задачу на сбор бюджетов.",
                             reply_markup=ROLE_KB)
        return
    if text == BTN_MANAGER:
        roles[chat_id] = "manager"
        await message.answer("Роль: менеджер. Отвечайте на запросы бюджетов.",
                             reply_markup=ROLE_KB)
        return

    role = roles.get(chat_id)
    if role is None:
        await message.answer("Сначала выберите роль кнопкой ниже.", reply_markup=ROLE_KB)
        return

    # analyst -> secretary agent
    if role == "analyst":
        reply = await secretary.handle_user(chat_id, text)
        if reply:
            await message.answer(reply, reply_markup=ROLE_KB)
        return

    # manager -> the relevant collector agent
    if role == "manager":
        active = CollectorRepository.get_active_by_chat_id(chat_id)
        if not active:
            await message.answer("Сейчас нет активных запросов на бюджет.",
                                 reply_markup=ROLE_KB)
            return
        agent = coordinator.get_collector_agent(active["id"])
        if agent is None:
            await message.answer("Не удалось найти подзадачу.", reply_markup=ROLE_KB)
            return
        reply = await agent.handle_user(chat_id, text)
        if reply:
            await message.answer(reply, reply_markup=ROLE_KB)
        return


async def main():
    init_db()
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
