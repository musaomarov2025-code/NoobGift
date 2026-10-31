import asyncio
import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)


logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
REWARD_PER_REFERRAL = float(os.getenv("REWARD_PER_REFERRAL", "3.5"))

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot_memory.db"

dp = Dispatcher()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL NOT NULL DEFAULT 0,
                referrals INTEGER NOT NULL DEFAULT 0,
                referred_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.commit()


def get_user(user_id: int):
    with sqlite3.connect(DB_PATH) as db:
        return db.execute(
            """
            SELECT user_id, username, first_name, balance, referrals
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def save_user(message: Message, referrer_id: int | None = None) -> bool:
    user = message.from_user

    if user is None:
        return False

    existing_user = get_user(user.id)

    with sqlite3.connect(DB_PATH) as db:
        if existing_user is None:
            db.execute(
                """
                INSERT INTO users (
                    user_id,
                    username,
                    first_name,
                    referred_by
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username or "",
                    user.first_name or "",
                    referrer_id,
                ),
            )

            if referrer_id and referrer_id != user.id:
                db.execute(
                    """
                    UPDATE users
                    SET balance = balance + ?,
                        referrals = referrals + 1
                    WHERE user_id = ?
                    """,
                    (REWARD_PER_REFERRAL, referrer_id),
                )

            db.commit()
            return True

        db.execute(
            """
            UPDATE users
            SET username = ?,
                first_name = ?
            WHERE user_id = ?
            """,
            (
                user.username or "",
                user.first_name or "",
                user.id,
            ),
        )
        db.commit()

    return False


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 Заработать"),
                KeyboardButton(text="📋 Задания"),
            ],
            [
                KeyboardButton(text="💳 Вывод"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def withdrawal_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐️ 15", callback_data="withdraw_15"),
                InlineKeyboardButton(text="⭐️ 25", callback_data="withdraw_25"),
            ],
            [
                InlineKeyboardButton(text="⭐️ 50", callback_data="withdraw_50"),
                InlineKeyboardButton(text="⭐️ 100", callback_data="withdraw_100"),
            ],
        ]
    )


async def get_referral_link(bot: Bot, user_id: int) -> str:
    bot_info = await bot.get_me()
    return f"https://t.me/{bot_info.username}?start=ref_{user_id}"


@dp.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
    referrer_id = None

    if message.text:
        parts = message.text.split(maxsplit=1)

        if len(parts) == 2 and parts[1].startswith("ref_"):
            try:
                referrer_id = int(parts[1].replace("ref_", ""))
            except ValueError:
                referrer_id = None

    is_new_user = save_user(message, referrer_id)

    if is_new_user and referrer_id and referrer_id != message.from_user.id:
        referral_notice = (
            f"\n\nТебя пригласил пользователь. "
            f"Ему начислено +{REWARD_PER_REFERRAL} ⭐️."
        )
    else:
        referral_notice = ""

    await message.answer(
        "🎁 Добро пожаловать в NoobGift!\n\n"
        "Выбери нужный раздел в меню ниже."
        f"{referral_notice}",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "💰 Заработать")
async def earn_handler(message: Message, bot: Bot) -> None:
    user = get_user(message.from_user.id)
    referral_link = await get_referral_link(bot, message.from_user.id)

    balance = user[3] if user else 0
    referrals = user[4] if user else 0

    share_text = quote(
        "Присоединяйся к NoobGift и зарабатывай ⭐️"
    )
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(referral_link)}&text={share_text}"
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

    await message.answer(
        "💰 Заработать\n\n"
        f"За каждого приглашённого друга: +{REWARD_PER_REFERRAL} ⭐️\n\n"
        f"🔗 Твоя реферальная ссылка:\n{referral_link}\n\n"
        f"👥 Приглашено друзей: {referrals}\n"
        f"💳 Твой баланс: {balance:.1f} ⭐️\n\n"
        "Делись ссылкой с друзьями и получай награды!",
        reply_markup=keyboard,
    )


@dp.message(F.text == "📋 Задания")
async def tasks_handler(message: Message) -> None:
    await message.answer(
        "📋 Задания\n\n"
        "Пока доступно одно задание:\n"
        "👥 Пригласи друга по своей ссылке\n"
        f"🎁 Награда: +{REWARD_PER_REFERRAL} ⭐️"
    )


@dp.message(F.text == "💳 Вывод")
async def withdrawal_handler(message: Message) -> None:
    user = get_user(message.from_user.id)
    balance = user[3] if user else 0

    await message.answer(
        f"💳 Вывод\n\n"
        f"Ваш баланс: {balance:.1f} ⭐️\n\n"
        "Выберите, сколько хотите вывести:",
        reply_markup=withdrawal_menu(),
    )


@dp.callback_query(F.data.startswith("withdraw_"))
async def withdraw_callback(callback) -> None:
    amount = float(callback.data.replace("withdraw_", ""))
    user = get_user(callback.from_user.id)
    balance = user[3] if user else 0

    if balance < amount:
        await callback.answer(
            f"Недостаточно средств. Нужно {amount:.0f} ⭐️.",
            show_alert=True,
        )
        return

    await callback.answer(
        "Заявка на вывод пока находится в разработке.",
        show_alert=True,
    )


@dp.message()
async def unknown_message_handler(message: Message) -> None:
    await message.answer(
        "Выбери раздел с помощью кнопок меню ниже.",
        reply_markup=main_menu(),
    )


async def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь его в переменные окружения BotHost."
        )

    init_db()

    async with Bot(TOKEN) as bot:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
