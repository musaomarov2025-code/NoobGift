import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8944743132:AAE5QUA4qMduCTmQM2FgLYJmBBlTsmaNcXg")

# Telegram ID админов
ADMIN_IDS = [8742164697]

DB_PATH = "/app/data/bot.db"

# Значения по умолчанию (потом меняются в админке)
DEFAULTS = {
    "task_reward": "0.25",    # награда за задание
    "ref_reward": "2",        # награда за друга
    "ref_tasks_needed": "3",  # сколько заданий должен выполнить друг
    "min_withdraw": "50",     # минимум для вывода
}
