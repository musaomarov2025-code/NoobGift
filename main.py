import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Переменная BOT_TOKEN не задана")


dp = Dispatcher()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Заработать"),
                KeyboardButton(text="Задания"),
            ],
            [
                KeyboardButton(text="Вывод"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите раздел",
    )


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🎁 Добро пожаловать в NoobGift!\n\n"
        "Выберите нужный раздел:",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "Заработать")
async def earn_handler(message: Message):
    await message.answer(
        "💰 Раздел «Заработать»\n\n"
        "Приглашайте друзей и получайте награды.",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "Задания")
async def tasks_handler(message: Message):
    await message.answer(
        "📋 Раздел «Задания»\n\n"
        "Здесь будут отображаться доступные задания.",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "Вывод")
async def withdraw_handler(message: Message):
    await message.answer(
        "💳 Раздел «Вывод»\n\n"
        "Ваш баланс: 0.0 ⭐️\n"
        "Выберите сумму для вывода.",
        reply_markup=main_keyboard(),
    )


async def main():
    logging.basicConfig(level=logging.INFO)

    async with Bot(token=BOT_TOKEN) as bot:
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
