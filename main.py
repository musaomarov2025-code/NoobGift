import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

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
    from aiogram.exceptions import TelegramForbiddenError
    while True:
        try:
            released = await database.process_holds()
            for user_id, amount, kind in released:
                try:
                    if kind == "ref":
                        text = f"🎉 Ваш реферал принёс <b>+{amount} ⭐️</b>!\nХолд переведён на баланс."
                    else:
                        text = f"🎉 <b>+{amount} ⭐️</b> переведено из холда на ваш баланс!"
                    await bot.send_message(user_id, text)
                except TelegramForbiddenError:
                    pass
                except Exception as e:
                    log.warning(f"hold notify {user_id}: {e}")
        except Exception as e:
            log.exception(f"hold_worker: {e}")
        await asyncio.sleep(60)


async def on_startup():
    await database.init()
    log.info("База загружена")

    # регистрируем роутеры (будут добавлены в следующих файлах)
    from handlers import user, tasks, admin  # noqa
    dp.include_router(admin.router)
    dp.include_router(tasks.router)
    dp.include_router(user.router)

    asyncio.create_task(hold_worker())
    log.info("Бот запущен")


async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановка бота")
