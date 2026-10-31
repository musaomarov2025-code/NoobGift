import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import Message


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot_memory.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

dp = Dispatcher()


def init_db() -> None:
    """Создаёт базу данных и таблицу пользователей."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def save_user(message: Message) -> None:
    """Сохраняет или обновляет пользователя в базе."""
    user = message.from_user

    if user is None:
        return

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT INTO users (
                chat_id,
                user_id,
                username,
                first_name,
                last_name
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                user_id = excluded.user_id,
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                message.chat.id,
                user.id,
                user.username or "",
                user.first_name or "",
                user.last_name or "",
            ),
        )
        connection.commit()


def get_saved_chat_ids() -> list[int]:
    """Возвращает список сохранённых чатов."""
    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute("SELECT chat_id FROM users")
        return [row[0] for row in cursor.fetchall()]


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    save_user(message)

    first_name = (
        message.from_user.first_name
        if message.from_user
        else "друг"
    )

    await message.answer(
        f"Привет, {first_name}! 👋\n"
        "Бот работает.\n\n"
        "Ты сохранён в памяти бота."
    )


@dp.message()
async def message_handler(message: Message) -> None:
    save_user(message)

    await message.answer(
        "Я получил твоё сообщение.\n"
        "Для запуска бота используй команду /start."
    )


async def notify_saved_users(bot: Bot) -> None:
    """Отправляет сообщение ранее сохранённым пользователям."""
    chat_ids = get_saved_chat_ids()

    for chat_id in chat_ids:
        try:
            await bot.send_message(
                chat_id,
                "Бот снова запущен! 👋",
            )
            await asyncio.sleep(0.05)
        except TelegramAPIError as error:
            logging.warning(
                "Не удалось отправить сообщение в чат %s: %s",
                chat_id,
                error,
            )


async def main() -> None:
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "Не задана переменная окружения BOT_TOKEN."
        )

    init_db()

    async with Bot(token=token) as bot:
        await notify_saved_users(bot)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
