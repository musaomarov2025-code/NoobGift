import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ"
ADMIN_ID = 123456789  # Твой Telegram ID
DB_PATH = "/app/data/bot.db"  # Для BotHost
# ============================================

# Создаем папку для БД, если ее нет (для хостинга)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def main():
    # Импорты внутри функции, чтобы избежать циклических зависимостей
    from database import init_db
    from user_handlers import user_router
    from admin_handlers import admin_router
    
    await init_db()
    
    dp.include_router(admin_router)
    dp.include_router(user_router)
    
    logging.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
