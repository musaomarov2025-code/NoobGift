from urllib.parse import quote
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

BTN_EARN = "💰 Заработать"
BTN_TASKS = "📋 Задания"
BTN_WITHDRAW = "💸 Вывод"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_EARN), KeyboardButton(text=BTN_TASKS)],
        [KeyboardButton(text=BTN_WITHDRAW)],
    ],
    resize_keyboard=True,
)


def ref_kb(link):
    share = (
        "https://t.me/share/url?url=" + quote(link)
        + "&text=" + quote("Забирай бесплатные звёзды! ⭐")
    )
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить ссылку друзьям", url=share)]
    ])


def task_kb(url):
    rows = []
    first = []
    if url:
        first.append(InlineKeyboardButton(text="🔎 Перейти", url=url))
    first.append(InlineKeyboardButton(
        text="✅ Подтвердить", callback_data="task_check"))
    rows.append(first)
    rows.append([InlineKeyboardButton(
        text="⏩ Пропустить", callback_data="task_skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def withdraw_kb(amount):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"💸 Вывести {amount:.2f} ⭐", callback_data="withdraw")
    ]])


# ---------- админка ----------

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm:settings")],
        [InlineKeyboardButton(text="🤝 Спонсоры", callback_data="adm:sponsors")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
    ])


def back_kb(to="adm:back"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=to)]
    ])


def settings_kb(labels):
    rows = [
        [InlineKeyboardButton(text=text, callback_data=f"set:{key}")]
        for key, text in labels.items()
    ]
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sponsors_kb(sponsors):
    rows = []
    for i, s in enumerate(sponsors, 1):
        mark = "✅" if s["enabled"] else "❌"
        key = "🔑" if s["api_key"] else "—"
        rows.append([InlineKeyboardButton(
            text=f"{i}. {mark} {s['name']} {key}",
            callback_data=f"sp:{s['name']}")])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sponsor_menu_kb(name, enabled):
    onoff = "❌ Выключить" if enabled else "✅ Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=onoff, callback_data=f"spt:{name}")],
        [
            InlineKeyboardButton(text="⬆️ Выше", callback_data=f"spu:{name}"),
            InlineKeyboardButton(text="⬇️ Ниже", callback_data=f"spd:{name}"),
        ],
        [InlineKeyboardButton(
            text="🔑 Добавить / изменить ключ", callback_data=f"spk:{name}")],
        [InlineKeyboardButton(
            text="🗑 Удалить ключ", callback_data=f"spx:{name}")],
        [InlineKeyboardButton(
            text="⬅️ Назад", callback_data="adm:sponsors")],
    ])
