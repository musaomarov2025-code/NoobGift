@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer("Привет! 👋 Рад тебя видеть!")
