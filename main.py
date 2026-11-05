import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ================= НАСТРОЙКИ =================
# Берем токен из переменной окружения BotHost
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Берем ID из переменной, если нет - используем твой
ADMIN_ID = int(os.getenv("ADMIN_ID", 8742164697)) 

DB_PATH = "/app/data/bot.db"
# ============================================

if not BOT_TOKEN:
    raise ValueError("❌ Ошибка: Переменная окружения BOT_TOKEN не задана!")

if "/" in DB_PATH:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Включаем HTML по умолчанию
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

async def main():
    from database import init_db
    from user_handlers import user_router
    from admin_handlers import admin_router, traffic_router
    
    await init_db()
    
    dp.include_router(admin_router)
    dp.include_router(traffic_router)
    dp.include_router(user_router)
    
    logging.info("Бот успешно запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
