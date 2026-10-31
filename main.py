from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


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
    )


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🎁 Добро пожаловать в NoobGift!\n\n"
        "Выберите раздел:",
        reply_markup=main_keyboard(),
    )
