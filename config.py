import json
import os
from datetime import datetime, timedelta, timezone

# Токен берётся из переменной BOT_TOKEN в настройках хостинга
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram ID админов (без кавычек)
ADMIN_IDS = [8742164697]

DB_PATH = "/app/data/stars.db"

# Адрес мини-приложения проверки (https://...), задаётся в переменной
# WEBAPP_URL на хостинге. Если пусто, проверка выключена.
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

BACKUP_HOURS = 6          # как часто бот присылает копию базы админу
DAILY_HOUR_MSK = 16       # время ежедневного уведомления (по Москве)
WITHDRAW_OPTIONS = [15, 20, 50, 100]

MSK = timezone(timedelta(hours=3))


def fmt(x):
    """15.0 -> '15', 0.25 -> '0.25'"""
    return f"{float(x):g}"


def fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, MSK).strftime("%d.%m.%Y %H:%M")


_DAILY_HEAD = "🎯 Звезды готовы к получению!"
_DAILY_BOLD = [{
    "type": "bold", "offset": 0,
    "length": len(_DAILY_HEAD.encode("utf-16-le")) // 2,
}]

# Значения по умолчанию (потом меняются в админке)
DEFAULTS = {
    "task_reward": "0.25",    # награда за задание
    "ref_reward": "2",        # награда за друга
    "ref_tasks_needed": "3",  # сколько заданий должен выполнить друг
    "payout_channel": "",     # канал выплат (@канал или ID)
    "ads_pointer": "0",
    "daily_enabled": "1",
    "daily_last": "",
    "daily_text": (
        _DAILY_HEAD + "\n\n"
        "Приглашай друзей и получай за каждого до 3⭐️\n"
        "Выполняй задания и получай за них до 12⭐️"
    ),
    "daily_entities": json.dumps(_DAILY_BOLD),
    "daily_btn_ref": "👥 Пригласить друга (+3⭐️)",
    "daily_btn_tasks": "🎯 Выполнить задания (+12⭐️)",
}
