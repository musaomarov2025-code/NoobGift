from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup


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
        one_time_keyboard=False,
        is_persistent=True,
    )


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "🎁 Добро пожаловать в NoobGift!\n\n"
        "Выбери раздел в меню ниже:",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "💰 Заработать")
async def earn_handler(message: Message) -> None:
    await message.answer("💰 Раздел «Заработать»")


@dp.message(F.text == "📋 Задания")
async def tasks_handler(message: Message) -> None:
    await message.answer("📋 Раздел «Задания»")


@dp.message(F.text == "💳 Вывод")
async def withdraw_handler(message: Message) -> None:
    await message.answer("💳 Раздел «Вывод»")
