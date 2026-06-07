import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession

from config import MANAGER_CHAT_ID, ALL_RESPONDENT_IDS, TELEGRAM_TOKEN, USE_PROXY, PROXY_URL
from agents.secretary import run_secretary_turn

load_dotenv()

# ---------- Настройка логирования ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- Создание бота с учётом прокси ----------
if USE_PROXY:
    session = AiohttpSession(proxy=PROXY_URL)
else:
    session = AiohttpSession()

bot = Bot(token=TELEGRAM_TOKEN, session=session)
dp = Dispatcher()

secretary_states = {}

def get_role(chat_id: int) -> str:
    if chat_id == MANAGER_CHAT_ID:
        return "manager"
    elif chat_id in ALL_RESPONDENT_IDS:
        return "respondent"
    return "unknown"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    role = get_role(message.chat.id)
    logger.info(f"User {message.chat.id} started bot, role: {role}")
    if role == "manager":
        secretary_states.pop(message.chat.id, None)
        await message.answer("Здравствуйте! Опишите задачу по сбору бюджетов.")
    elif role == "respondent":
        await message.answer("Добрый день! Я бот-помощник по сбору бюджетов. Ожидайте запрос.")
    else:
        await message.answer("Доступ запрещён.")

@dp.message()
async def handle_message(message: types.Message):
    role = get_role(message.chat.id)
    logger.info(f"Message from {message.chat.id} (role: {role}): {message.text}")

    if role == "manager":
        if message.chat.id not in secretary_states:
            state = {"messages": [], "task_params": {}, "missing_fields": [], "next_action": ""}
        else:
            state = secretary_states[message.chat.id]

        state["messages"].append({"role": "user", "content": message.text})
        try:
            new_state = run_secretary_turn(state)
        except Exception as e:
            logger.exception("Error in secretary processing")
            await message.answer("Произошла ошибка при обработке запроса. Попробуйте позже.")
            return
        secretary_states[message.chat.id] = new_state

        # Отправляем последнее сообщение ассистента
        for msg in reversed(new_state["messages"]):
            if msg["role"] == "assistant":
                await message.answer(msg["content"])
                break

        if new_state.get("next_action") == "complete":
            logger.info("Secretary task is complete, launching coordinator")
            await message.answer("Задача передана Координатору. Ожидайте результатов сбора.")
            # Здесь будет вызов координатора

    elif role == "respondent":
        await message.answer("Пока нет активного сбора. Ждите запрос от координатора.")
    else:
        await message.answer("Неизвестная роль.")

async def main():
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())