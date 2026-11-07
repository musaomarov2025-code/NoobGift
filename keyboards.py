from urllib.parse import quote

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import WITHDRAW_OPTIONS, fmt

BTN_EARN = "⭐ Заработать"
BTN_TASKS = "💎 Задания"
BTN_WITHDRAW = "🎁 Вывести"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_EARN), KeyboardButton(text=BTN_TASKS)],
        [KeyboardButton(text=BTN_WITHDRAW)],
    ],
    resize_keyboard=True,
)


def ik(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def b(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


# ---------- для пользователей ----------

def ref_kb(link):
    share = (
        "https://t.me/share/url?url=" + quote(link)
        + "&text=" + quote("Забирай бесплатные звёзды! ⭐")
    )
    return ik([[InlineKeyboardButton(
        text="Отправить ссылку друзьям", url=share)]])


def task_kb(url):
    first = []
    if url:
        first.append(InlineKeyboardButton(text="🔎 Перейти", url=url))
    first.append(b("✅ Подтвердить", "task_check"))
    return ik([first, [b("⏩ Пропустить", "task_skip")]])


def withdraw_kb():
    btns = [b(f"{n} ⭐️", f"withdraw:{n}") for n in WITHDRAW_OPTIONS]
    return ik([btns[i:i + 2] for i in range(0, len(btns), 2)])


def req_notify_kb(wid):
    return ik([[b("Открыть заявку", f"rq:open:{wid}")]])


# ---------- админка ----------

def admin_kb():
    return ik([
        [b("⚙️ Настройки", "adm:settings"), b("🤝 Спонсоры", "adm:sponsors")],
        [b("📣 Показы", "adm:ads"), b("📨 Рассылка", "adm:bc")],
        [b("🎯 Ежедневное", "adm:daily"), b("💸 Заявки", "adm:reqs")],
        [b("📊 Статистика", "adm:stats"), b("💾 База данных", "adm:db")],
    ])


def back_kb(to="adm:back"):
    return ik([[b("⬅️ Назад", to)]])


def settings_kb(labels):
    rows = [[b(text, f"set:{key}")] for key, text in labels.items()]
    rows.append([b("⬅️ Назад", "adm:back")])
    return ik(rows)


def sponsors_kb(sponsors):
    rows = []
    for i, s in enumerate(sponsors, 1):
        mark = "✅" if s["enabled"] else "❌"
        key = "🔑" if s["api_key"] else "—"
        rows.append([b(f"{i}. {mark} {s['name']} {key}", f"sp:{s['name']}")])
    rows.append([b("⬅️ Назад", "adm:back")])
    return ik(rows)


def sponsor_menu_kb(name, enabled):
    onoff = "❌ Выключить" if enabled else "✅ Включить"
    return ik([
        [b(onoff, f"spt:{name}")],
        [b("⬆️ Выше", f"spu:{name}"), b("⬇️ Ниже", f"spd:{name}")],
        [b("🔑 Добавить / изменить ключ", f"spk:{name}")],
        [b("🗑 Удалить ключ", f"spx:{name}")],
        [b("⬅️ Назад", "adm:sponsors")],
    ])


# показы и рассылка

def ads_kb(ads):
    icons = {"photo": "🖼", "video": "🎬", "animation": "🎞",
             "sticker": "😀"}
    rows = []
    for a in ads:
        mark = "✅" if a["enabled"] else "❌"
        snippet = (a["text"] or "").replace("\n", " ")[:22]
        rows.append([b(
            f"{a['id']}. {mark} {icons.get(a['kind'], '📝')} {snippet}",
            f"ad:open:{a['id']}")])
    rows.append([b("➕ Добавить показ", "ad:new")])
    rows.append([b("⬅️ Назад", "adm:back")])
    return ik(rows)


def ad_menu_kb(ad):
    onoff = "❌ Выключить" if ad["enabled"] else "✅ Включить"
    i = ad["id"]
    return ik([
        [b(onoff, f"ad:tg:{i}")],
        [b("✏️ Пост", f"ad:ep:{i}"), b("🔘 Кнопки", f"ad:eb:{i}")],
        [b("🗑 Удалить", f"ad:del:{i}")],
        [b("⬅️ К списку", "adm:ads")],
    ])


def ad_delete_kb(ad_id):
    return ik([[b("🗑 Да, удалить", f"ad:delok:{ad_id}"),
                b("Отмена", f"ad:open:{ad_id}")]])


def ad_save_kb():
    return ik([[b("✅ Сохранить", "ad:save"), b("❌ Отмена", "adm:ads")]])


def wd_cancel_kb():
    return ik([[b("❌ Отменить вывод", "wd_cancel")]])


def bc_groups_kb(counts):
    names = [
        ("all", "👥 Всем"),
        ("new", "🆕 Новым (7 дней)"),
        ("active", "🔥 Активным (3 дня)"),
        ("inactive", "😴 Неактивным (3+ дня)"),
        ("rich", f"💰 С балансом от {min(WITHDRAW_OPTIONS)} ⭐"),
    ]
    rows = [[b(f"{t} · {counts[k]}", f"bcg:{k}")] for k, t in names]
    rows.append([b("❌ Отмена", "adm:back")])
    return ik(rows)


def bc_confirm_kb():
    return ik([[b("🚀 Отправить всем", "bc:go"), b("❌ Отмена", "adm:back")]])


def daily_kb(enabled):
    onoff = "🔕 Выключить" if enabled else "🔔 Включить"
    return ik([
        [b(onoff, "daily:toggle")],
        [b("✏️ Текст", "daily:text"), b("🔘 Кнопки", "daily:btns")],
        [b("📤 Тест мне", "daily:test")],
        [b("⬅️ Назад", "adm:back")],
    ])


# заявки, статистика, пользователи, база

def reqs_kb(rows, history=False):
    out = []
    for r in rows:
        name = f"@{r['username']}" if r["username"] else (
            r["first_name"] or str(r["user_id"]))
        icon = {"paid": "✅", "rejected": "❌"}.get(r["status"], "⏳")
        out.append([b(
            f"{icon} #{r['id']} · {fmt(r['amount'])} ⭐ · {name}",
            f"rq:open:{r['id']}")])
    if history:
        out.append([b("⏳ Ожидающие", "adm:reqs")])
    else:
        out.append([b("📜 История", "rq:hist")])
    out.append([b("⬅️ Назад", "adm:back")])
    return ik(out)


def req_kb(wid, uid, status):
    rows = []
    if status == "new":
        rows.append([b("✅ Выплачено", f"rq:pay:{wid}"),
                     b("❌ Отклонить", f"rq:rej:{wid}")])
    rows.append([b("👤 Пользователь", f"usr:open:{uid}")])
    rows.append([b("⬅️ К заявкам", "adm:reqs")])
    return ik(rows)


def stats_kb():
    return ik([
        [b("🔎 Найти пользователя", "adm:find"),
         b("🏆 Топ рефералов", "adm:top")],
        [b("⬅️ Назад", "adm:back")],
    ])


def user_tools_kb(uid, banned):
    ban = "✅ Разбанить" if banned else "🚫 Забанить"
    return ik([
        [b("➕ Баланс", f"usr:add:{uid}"), b("➖ Баланс", f"usr:sub:{uid}")],
        [b(ban, f"usr:ban:{uid}")],
        [b("⬅️ Статистика", "adm:stats")],
    ])


def db_kb():
    return ik([
        [b("⬇️ Скачать БД", "db:dl"), b("⬆️ Загрузить БД", "db:ul")],
        [b("⬅️ Назад", "adm:back")],
    ])
