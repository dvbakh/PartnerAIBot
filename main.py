import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from storage.db import init_db
import sqlite3
from storage.db import DB_PATH

from config import (
    MANAGER_CHAT_ID,
    TELEGRAM_TOKEN,
    USE_PROXY,
    PROXY_URL,
    GEO_STRUCTURE
)

from agents.secretary import SecretaryAgent
from agents.coordinator import Coordinator
from agents.collector import CollectorAgent

from storage.task_repository import TaskRepository
from storage.collector_repository import CollectorRepository

from utils.sheets import append_budget_rows


# ---------------- logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -------------- proxy ---------
if USE_PROXY:
    session = AiohttpSession(proxy=PROXY_URL)
else:
    session = AiohttpSession()

bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()

# ---------------- state ----------------
secretary_states = {}


# =========================================================
# ROLE CHECK
# =========================================================
def is_manager(chat_id: int) -> bool:
    return chat_id == MANAGER_CHAT_ID


# =========================================================
# START
# =========================================================
@dp.message(Command("start"))
async def start(message: types.Message):
    if is_manager(message.chat.id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE collectors SET status='cancelled' WHERE respondent_chat_id=? AND status IN ('created','contacted','waiting_response')",
            (message.chat.id,))
        conn.commit()
        conn.close()
        secretary_states[message.chat.id] = SecretaryAgent.create_state()
        await message.answer("Привет! Опиши задачу для сбора бюджетов.")
    else:
        await message.answer("Нет доступа.")


# =========================================================
# MAIN HANDLER
# =========================================================
@dp.message()
async def create_and_run_task(task_state: dict, bot: Bot):
    """Создаёт задачу и запускает координатора."""
    from models.task import Task
    task_obj = Task(
        month=task_state["month"],
        geo_list=task_state["geo_list"],
        deadline=task_state["deadline"],
        status="created"
    )
    task_id = TaskRepository.create(task_obj)
    logger.info(f"Task created: {task_id}")

    task_obj.id = task_id
    coordinator = Coordinator(task_obj)
    coordinator.create_collectors()
    await coordinator.start_collection(bot)


@dp.message()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    text = message.text
    logger.info(f"Message from {chat_id}: {text}")

    # ===================== ТЕСТОВЫЙ РЕЖИМ =====================
    if chat_id in test_states:
        role = test_states[chat_id]

        # Выбор роли
        if text == "Менеджер":
            test_states[chat_id] = "manager"
            await message.answer("Ты менеджер. Опиши задачу.", reply_markup=role_keyboard)
            return
        if text == "Респондент":
            test_states[chat_id] = "collector"
            await message.answer("Ты респондент. Отправь бюджеты.", reply_markup=role_keyboard)
            return

        if role is None:
            await message.answer("Сначала выбери роль кнопкой.", reply_markup=role_keyboard)
            return

        # === Роль МЕНЕДЖЕР ===
        if role == "manager":
            state = secretary_states.get(chat_id)
            if not state:
                state = SecretaryAgent.create_state()

            result = SecretaryAgent.process_message(state, text)
            secretary_states[chat_id] = result["state"]
            await message.answer(result["message"])

            if result["action"] == "create_task":
                await create_and_run_task(result["state"], bot)
                secretary_states.pop(chat_id, None)
                await message.answer("Задача создана, сборщики оповещены.")
            return

        # === Роль РЕСПОНДЕНТ ===
        if role == "collector":
            # Ищем активного сборщика именно для этого чата
            collector = CollectorRepository.get_active_by_chat_id(chat_id)
            if not collector:
                await message.answer("Нет активной задачи для сбора бюджетов. Дождитесь запроса.")
                return

            try:
                records = CollectorAgent.extract_budgets(text)
                if records:
                    CollectorAgent.save_records(
                        task_id=collector["task_id"],
                        geo=collector["geo"],
                        channel=collector["channel"],
                        records=records
                    )
                    CollectorRepository.update_status(collector["id"], "completed")
                    await message.answer("Принято, спасибо!")

                    remaining = CollectorRepository.get_by_task(collector["task_id"])
                    if all(r["status"] == "completed" for r in remaining):
                        logger.info("All collectors completed")
                        await message.answer("Все данные собраны.")
                else:
                    await message.answer("Не удалось распознать бюджеты. Попробуйте ещё.")
            except Exception as e:
                logger.exception("Collector error")
                await message.answer("Ошибка обработки.")
            return

    # ===================== ОБЫЧНЫЙ РЕЖИМ =====================
    if is_manager(chat_id):
        collector = CollectorRepository.get_active_by_chat_id(chat_id)
        if collector:
            # Сначала пытаемся обработать как ответ респондента
            records = CollectorAgent.extract_budgets(text)
            if records:
                CollectorAgent.save_records(
                    task_id=collector["task_id"],
                    geo=collector["geo"],
                    channel=collector["channel"],
                    records=records
                )
                CollectorRepository.update_status(collector["id"], "completed")
                await message.answer("Принято, спасибо!")

                remaining = CollectorRepository.get_by_task(collector["task_id"])
                if all(r["status"] == "completed" for r in remaining):
                    logger.info("All collectors completed")
                    await message.answer("Все данные собраны.")
                secretary_states.pop(chat_id, None)
                return
            else:
                # Не получилось извлечь бюджеты – отменяем сборщика, идём в SecretaryAgent
                CollectorRepository.update_status(collector["id"], "cancelled")

        # SecretaryAgent
        state = secretary_states.get(chat_id)
        if not state:
            state = SecretaryAgent.create_state()

        result = SecretaryAgent.process_message(state, text)
        secretary_states[chat_id] = result["state"]
        await message.answer(result["message"])

        if result["action"] == "create_task":
            await create_and_run_task(result["state"], bot)
            secretary_states.pop(chat_id, None)
        return

    # Обычный респондент (не менеджер)
    collector = CollectorRepository.get_active_by_chat_id(chat_id)
    if collector:
        try:
            records = CollectorAgent.extract_budgets(text)
            if not records:
                await message.answer("Не удалось распознать данные.")
                return
            CollectorAgent.save_records(
                task_id=collector["task_id"],
                geo=collector["geo"],
                channel=collector["channel"],
                records=records
            )
            CollectorRepository.update_status(collector["id"], "completed")
            await message.answer("Принято, спасибо!")

            remaining = CollectorRepository.get_by_task(collector["task_id"])
            if all(r["status"] == "completed" for r in remaining):
                logger.info("All collectors completed")
                await message.answer("Все данные собраны.")
        except Exception as e:
            logger.exception("Collector error")
            await message.answer("Ошибка обработки.")
        return

    await message.answer("Нет активных задач.")

    # ------------------------------------------------------------
    # 3. Ни менеджер, ни активный респондент
    # ------------------------------------------------------------
    await message.answer("Нет активных задач.")

    # =====================================================
    # 2. COLLECTOR FLOW (MANAGERS)
    # =====================================================
    collector = CollectorRepository.get_active_by_chat_id(chat_id)

    if not collector:
        await message.answer("Нет активных задач.")
        return

    try:
        # 1. extract budgets
        records = CollectorAgent.extract_budgets(text)

        if not records:
            await message.answer("Не удалось распознать данные.")
            return

        # 2. save to DB
        CollectorAgent.save_records(
            task_id=collector["task_id"],
            geo=collector["geo"],
            channel=collector["channel"],
            records=records
        )

        # 3. mark completed
        CollectorRepository.update_status(
            collector["id"],
            "completed"
        )

        await message.answer("Принято, спасибо!")

        # =====================================================
        # 4. CHECK IF TASK IS FINISHED → WRITE TO SHEETS
        # =====================================================
        remaining = CollectorRepository.get_by_task(
            collector["task_id"]
        )

        all_done = all(r["status"] == "completed" for r in remaining)

        if all_done:

            logger.info("All collectors completed → exporting to Google Sheets")

            # агрегируем данные из БД
            all_rows = []

            for r in remaining:

                # здесь можно потом заменить на SQL join
                # сейчас упрощённо через records уже записанные

                pass

            # берем напрямую из budget_records было бы лучше,
            # но оставим через идею:
            # → Coordinator финализирует

            await message.answer("Все данные собраны. Формирую отчёт...")

            # TO_DO: здесь можно добавить TaskRepository.get_budgets(task_id)

    except Exception as e:
        logger.exception("Collector error")
        await message.answer("Ошибка обработки.")


# =========================================================
# RUN
# =========================================================
async def main():
    init_db()
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())