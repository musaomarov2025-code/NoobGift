import logging
import os
import sys

import telebot
from telebot.apihelper import ApiTelegramException


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logging.critical("Переменная окружения BOT_TOKEN не задана")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)


@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message) -> None:
    """Отправляет приветствие при выполнении команды /start."""
    try:
        bot.reply_to(message, "Привет")
    except ApiTelegramException:
        logging.exception("Ошибка отправки сообщения")


if __name__ == "__main__":
    logging.info("Бот запущен")
    bot.infinity_polling(skip_pending=True)
