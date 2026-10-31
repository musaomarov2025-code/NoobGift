import os
import asyncio
import sqlite3
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

db = sqlite3.connect("bot_memory.db")
db.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY
)
""")
db.commit()


@dp.message(CommandStart())
async def start_handler(message: Message):
    if message.chat.type == "private":
        db.execute(
            "INSERT OR IGNORE INTO users (chat_id) VALUES (?)",
            (message.chat.id,)
        )
        db.commit()

    await message.answer(
        "Привет! 👋 Рад тебя видеть!\n\n"
        "Добро пожаловать! ❤️"
    )


async def startup_greeting():
    users = db.execute("SELECT chat_id FROM users").fetchall()

    for (chat_id,) in users:
        try:
            await bot.send_message(
                chat_id,
                "Привет! 👋 Бот снова запущен!\n\n"
                "Рад тебя видеть! ❤️"
            )
            await asyncio.sleep(0.05)

        except TelegramForbiddenError:
            logging.info("Пользователь %s заблокировал бота", chat_id)

        except Exception as error:
            logging.warning("Ошибка отправки %s: %s", chat_id, error)


async def main():
    logging.basicConfig(level=logging.INFO)

    print("Бот запускается...")

    await startup_greeting()

    print("Бот работает!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
