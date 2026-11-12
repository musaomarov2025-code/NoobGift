import json
import os
from datetime import datetime, timedelta, timezone

# Токен берётся из переменной BOT_TOKEN в настройках хостинга
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Telegram ID админов. Можно задать переменной ADMIN_IDS (через запятую).
def _admin_ids():
    raw = os.getenv("ADMIN_IDS", "")
    ids = [int(x) for x in raw.replace(" ", "").split(",")
           if x.lstrip("-").isdigit()]
    return ids or [8742164697]


ADMIN_IDS = _admin_ids()

# Имя файла базы. У каждого бота должно быть своё: переменная DB_NAME.
DB_NAME = os.getenv("DB_NAME", "stars.db")
DB_PATH = f"/app/data/{DB_NAME}"

BACKUP_HOURS = 6          # как часто бот присылает копию базы админу
DAILY_HOUR_MSK = 16       # время ежедневного уведомления (по Москве)
REMIND_HOUR_MSK = 17      # напоминание неактивным (по Москве)
REMIND_EVERY_DAYS = 5     # как часто напоминать одному человеку
REPORT_HOUR_MSK = 9       # утренний отчёт админу (по Москве)
WITHDRAW_OPTIONS = [15, 20, 50, 100]

MSK = timezone(timedelta(hours=3))


def fmt(x):
    """15.0 -> '15', 0.25 -> '0.25'"""
    return f"{float(x):g}"


def fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, MSK).strftime("%d.%m.%Y %H:%M")


def fmt1(x):
    """2 -> '2.0', 0.25 -> '0.25'"""
    x = float(x)
    return f"{x:.1f}" if x == int(x) else f"{x:g}"


def fmt_bal(x):
    """2.0 -> '2', 2.25 -> '2.25', 2.5 -> '2.5'"""
    return f"{float(x):.2f}".rstrip("0").rstrip(".") or "0"


def plural(n, one, few, many):
    """plural(3, 'задание', 'задания', 'заданий')"""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    r = n % 10
    return one if r == 1 else few if 2 <= r <= 4 else many


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
    "withdraw_tasks": "3",    # сколько заданий выполнить для вывода
    "start_bonus": "2",       # звёзд за запуск бота (один раз)
    "remind_enabled": "1",
    "remind_style": "success",
    "remind_text": (
        "👋 <b>{name}, ты давно не заходил!</b>\n\n"
        "На твоём балансе {balance} ⭐️. "
        "Выполни пару заданий и выведи их 👇"
    ),
    "remind_text_zero": (
        "⭐️ <b>Тебя давно не было!</b>\n\n"
        "За это время появились новые задания. "
        "Заходи и забирай звёзды 👇"
    ),
    "report_enabled": "1",
    "daily_style_ref": "",
    "daily_style_tasks": "",
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
