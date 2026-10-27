import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import config
import database

# ==== ПРОВЕРКА ТОКЕНА ====
if not config.BOT_TOKEN:
    print("❌ BOT_TOKEN не задан! Добавь переменную окружения BOT_TOKEN на BotHost.")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


async def hold_worker():
    """Раз в минуту переводит созревший холд на баланс и уведомляет юзеров."""
    while True:
        try:
            released = await database.process_holds()
            for user_id, amount, kind in released:
                try:
                    if kind == "ref":
                        text = f"🎉 Ваш реферал принёс <b>+{amount:.2f} ⭐️</b>!\nХолд переведён на баланс."
                    else:
                        text = f"🎉 <b>+{amount:.2f} ⭐️</b> переведено из холда на ваш баланс!"
                    await bot.send_message(user_id, text)
                except TelegramForbiddenError:
                    pass  # Юзер заблокировал бота
                except Exception as e:
                    log.warning(f"hold notify {user_id}: {e}")
        except Exception as e:
            log.exception(f"hold_worker: {e}")
        
        await asyncio.sleep(60)  # Проверка каждую минуту


async def autopost_worker():
    """Отправляет автопост каждые 24 часа."""
    while True:
        try:
            autopost = await database.get_setting("autopost")
            if autopost and autopost.get("enabled"):
                log.info("Начинаю рассылку автопоста...")
                data = await database.export_data()
                users = list(data["users"].keys())
                
                success = 0
                for uid in users:
                    try:
                        if autopost.get("media"):
                            if autopost["media"]["type"] == "photo":
                                await bot.send_photo(uid, autopost["media"]["file_id"], caption=autopost["text"])
                            elif autopost["media"]["type"] == "video":
                                await bot.send_video(uid, autopost["media"]["file_id"], caption=autopost["text"])
                        else:
                            await bot.send_message(uid, autopost["text"])
                        success += 1
                        await asyncio.sleep(0.05)  # Защита от FloodWait
                    except TelegramForbiddenError:
                        pass  # Юзер заблокировал бота
                    except TelegramBadRequest:
                        pass
                    except Exception as e:
                        log.warning(f"autopost to {uid}: {e}")
                
                log.info(f"Автопост завершен. Доставлено: {success}/{len(users)}")
        except Exception as e:
            log.exception(f"autopost_worker: {e}")
        
        await asyncio.sleep(86400)  # 24 часа (86400 секунд)


async def on_startup():
    await database.init()
    log.info("База загружена")

    # Регистрируем роутеры
    from handlers import user, tasks, admin
    dp.include_router(admin.router)
    dp.include_router(tasks.router)
    dp.include_router(user.router)

    # Запускаем фоновые задачи
    asyncio.create_task(hold_worker())
    asyncio.create_task(autopost_worker())
    
    log.info("Бот успешно запущен и готов к работе!")


async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка бота")
