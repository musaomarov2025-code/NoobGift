import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# ================= НАСТРОЙКИ =================
BOT_TOKEN = "8944743132:AAE5QUA4qMduCTmQM2FgLYJmBBlTsmaNcXg"  # Вставь токен от BotFather
ADMIN_ID = 8742164697  # Твой Telegram ID (узнать в @userinfobot)
DB_PATH = "/app/data/bot.db"  # Для BotHost. Если тестируешь на ПК, укажи просто "bot.db"
# ============================================

# Создаем папку для БД, если ее нет (защита для хостинга)
if "/" in DB_PATH:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def main():
    # Импорты внутри функции, чтобы избежать циклических зависимостей
    from database import init_db
    from user_handlers import user_router
    from admin_handlers import admin_router, traffic_router
    
    # Инициализация БД
    await init_db()
    
    # Подключение роутеров (порядок важен!)
    dp.include_router(admin_router)   # Админка (фильтр по ADMIN_ID)
    dp.include_router(traffic_router) # Команды /stat_XXXX
    dp.include_router(user_router)    # Все остальные (юзеры)
    
    logging.info("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
