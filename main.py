import asyncio
import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot_memory.db"

dp = Dispatcher()

REWARD_PER_REFERRAL = 3.5
MIN_WITHDRAWAL = 15.0


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="💰 Заработать"),
            KeyboardButton(text="📋 Задания"),
        ],
        [
            KeyboardButton(text="💸 Вывод"),
        ],
    ],
    resize_keyboard=True,
)


def db_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with db_connection() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                balance REAL DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                referred_by INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(users)").fetchall()
        }

        if "balance" not in columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0"
            )

        if "referrals" not in columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN referrals INTEGER DEFAULT 0"
            )

        if "referred_by" not in columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL"
            )

        db.commit()


def save_user(message: Message, referral_id: int | None = None):
    user = message.from_user

    if user is None:
        return

    with db_connection() as db:
        existing = db.execute(
            "SELECT user_id FROM users WHERE chat_id = ?",
            (message.chat.id,),
        ).fetchone()

        if existing:
            db.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?
                WHERE chat_id = ?
                """,
                (
                    user.username or "",
                    user.first_name or "",
                    message.chat.id,
                ),
            )
        else:
            valid_referral = (
                referral_id
                if referral_id and referral_id != user.id
                else None
            )

            db.execute(
                """
                INSERT INTO users (
                    chat_id,
                    user_id,
                    username,
                    first_name,
                    referred_by
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message.chat.id,
                    user.id,
                    user.username or "",
                    user.first_name or "",
                    valid_referral,
                ),
            )

            if valid_referral:
                db.execute(
                    """
                    UPDATE users
                    SET referrals = referrals + 1,
                        balance = balance + ?
                    WHERE user_id = ?
                    """,
                    (REWARD_PER_REFERRAL, valid_referral),
                )

        db.commit()


def get_user(user_id: int):
    with db_connection() as db:
        return db.execute(
            """
            SELECT user_id, balance, referrals
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def get_referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


@dp.message(CommandStart())
async def start_handler(message: Message):
    referral_id = None

    if message.text:
        parts = message.text.split(maxsplit=1)

        if len(parts) == 2 and parts[1].startswith("ref_"):
            try:
                referral_id = int(parts[1].replace("ref_", ""))
            except ValueError:
                referral_id = None

    save_user(message, referral_id)

    first_name = message.from_user.first_name if message.from_user else "друг"

    await message.answer(
        f"Привет, {first_name}! 👋\n\n"
        "Добро пожаловать в бот NoobGift.\n"
        "Выбери нужный раздел ниже:",
        reply_markup=main_keyboard,
    )


@dp.message(F.text == "💰 Заработать")
async def earn_handler(message: Message, bot: Bot):
    save_user(message)

    user = message.from_user
    if user is None:
        return

    bot_info = await bot.get_me()
    referral_link = get_referral_link(bot_info.username, user.id)

    share_text = quote(
        "Присоединяйся к NoobGift и зарабатывай ⭐️"
    )
    share_url = (
        "https://t.me/share/url"
        f"?url={quote(referral_link)}"
        f"&text={share_text}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Отправить ссылку друзьям",
                    url=share_url,
                )
            ]
        ]
    )

    saved_user = get_user(user.id)
    referrals = saved_user[2] if saved_user else 0

    await message.answer(
        "💰 Заработать\n\n"
        f"За каждого приглашённого друга: "
        f"+{REWARD_PER_REFERRAL} ⭐️\n\n"
        "Твоя реферальная ссылка:\n"
        f"{referral_link}\n\n"
        f"Приглашено друзей: {referrals}\n\n"
        "Делись ссылкой и получай награды!",
        reply_markup=keyboard,
    )


@dp.message(F.text == "📋 Задания")
async def tasks_handler(message: Message):
    save_user(message)

    await message.answer(
        "📋 Задания\n\n"
        "Пока доступных заданий нет.\n"
        "Новые задания появятся здесь позже.",
        reply_markup=main_keyboard,
    )


@dp.message(F.text == "💸 Вывод")
async def withdraw_handler(message: Message):
    save_user(message)

    user = message.from_user
    if user is None:
        return

    saved_user = get_user(user.id)
    balance = saved_user[1] if saved_user else 0.0

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐️ 15",
                    callback_data="withdraw_15",
                ),
                InlineKeyboardButton(
                    text="⭐️ 25",
                    callback_data="withdraw_25",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⭐️ 50",
                    callback_data="withdraw_50",
                ),
                InlineKeyboardButton(
                    text="⭐️ 100",
                    callback_data="withdraw_100",
                ),
            ],
        ]
    )

    await message.answer(
        f"💸 Ваш баланс: {balance:.1f} ⭐️\n\n"
        "Выберите, сколько хотите вывести:",
        reply_markup=keyboard,
    )


@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw_callback(callback: CallbackQuery):
    if callback.from_user is None:
        return

    amount = float(callback.data.replace("withdraw_", ""))
    user = get_user(callback.from_user.id)
    balance = user[1] if user else 0.0

    if amount < MIN_WITHDRAWAL:
        await callback.answer(
            f"Минимальная сумма вывода — {MIN_WITHDRAWAL} ⭐️",
            show_alert=True,
        )
        return

    if balance < amount:
        await callback.answer(
            f"Недостаточно средств. Ваш баланс: {balance:.1f} ⭐️",
            show_alert=True,
        )
        return

    await callback.answer("Заявка принята!")

    if callback.message:
        await callback.message.answer(
            f"✅ Заявка на вывод {amount:.0f} ⭐️ принята.\n"
            "Администратор обработает её вручную."
        )


@dp.message()
async def other_message_handler(message: Message):
    save_user(message)

    await message.answer(
        "Используй кнопки меню ниже 👇",
        reply_markup=main_keyboard,
    )


async def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "Не задана переменная окружения BOT_TOKEN"
        )

    init_db()

    bot = Bot(token=token)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
