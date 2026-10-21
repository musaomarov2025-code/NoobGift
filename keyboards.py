from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS


# ==========================================
# УТИЛИТА: СБОРКА КЛАВИАТУРЫ ИЗ РЯДОВ
# ==========================================
def build_kb_from_rows(rows):
    """
    rows — список рядов, каждый ряд — список словарей:
    {"text": str, "url": str, "color": str|None}
    Возвращает InlineKeyboardMarkup или None, если рядов нет.
    """
    if not rows:
        return None
    builder = InlineKeyboardBuilder()
    for row in rows:
        buttons = []
        for btn in row:
            style = btn.get("color")
            if style in ("None", "", None):
                style = None
            buttons.append(InlineKeyboardButton(
                text=btn["text"],
                url=btn["url"],
                style=style
            ))
        if buttons:
            builder.row(*buttons)
    return builder.as_markup()


# ==========================================
# ГЛАВНОЕ МЕНЮ И НАВИГАЦИЯ
# ==========================================
def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Заработать звезды',
        callback_data="menu_earn",
        icon_custom_emoji_id="6005661956931850799",
        style="primary"
    ))
    builder.row(
        InlineKeyboardButton(text='Рефералы', callback_data="menu_refs", icon_custom_emoji_id="5278467510604160626"),
        InlineKeyboardButton(text='Профиль', callback_data="menu_profile", icon_custom_emoji_id="5258011929993026890")
    )
    builder.row(
        InlineKeyboardButton(text='Вывод', callback_data="menu_withdraw", icon_custom_emoji_id="6037408065966312773"),
        InlineKeyboardButton(text='Статистика', callback_data="menu_stats", icon_custom_emoji_id="6154657967317717391")
    )
    builder.row(InlineKeyboardButton(
        text='Инструкция',
        callback_data="menu_instruction",
        icon_custom_emoji_id="5334544901428229844"
    ))
    return builder.as_markup()


def back_kb(target="menu_back"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Назад',
        callback_data=target,
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()


def notify_task_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Открыть задания",
        callback_data="menu_earn",
        style="primary",
        icon_custom_emoji_id="5472033358693280429"
    ))
    return builder.as_markup()


# ==========================================
# ОП (BOTOHUB) И ЗАДАНИЯ
# ==========================================
def op_screen_kb(items, confirm_callback="op_check"):
    builder = InlineKeyboardBuilder()
    for i, (op_key, title, url, passed) in enumerate(items, 1):
        prefix = "✅ " if passed else ""
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{title} {i}",
            url=url,
            icon_custom_emoji_id="5472033358693280429",
            style="primary"
        ))
    builder.row(InlineKeyboardButton(
        text="Я подписался",
        callback_data=confirm_callback,
        icon_custom_emoji_id="5411197345968701560",
        style="success"
    ))
    return builder.as_markup()


def task_kb(task_url):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Сделать задание',
        url=task_url,
        icon_custom_emoji_id="5472033358693280429",
        style="primary"
    ))
    builder.row(
        InlineKeyboardButton(text='Проверить', callback_data="check_task", icon_custom_emoji_id="5251503375207392582", style="success"),
        InlineKeyboardButton(text='Пропустить', callback_data="skip_task", icon_custom_emoji_id="6311812139233316820", style="danger")
    )
    builder.row(InlineKeyboardButton(
        text='Назад',
        callback_data="menu_back",
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()


# ==========================================
# ВЫВОД
# ==========================================
def withdraw_kb():
    builder = InlineKeyboardBuilder()
    row_buttons = []
    for amount in WITHDRAW_AMOUNTS:
        row_buttons.append(InlineKeyboardButton(text=str(amount), callback_data=f"wd_{amount}", style="primary"))
    builder.row(*row_buttons)
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()


# ==========================================
# СТАТИСТИКА (ТОПЫ)
# ==========================================
def stats_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Топ по балансу', callback_data="top_balance", icon_custom_emoji_id="5417924076503062111", style="primary"))
    builder.row(
        InlineKeyboardButton(text='Топ по реф...', callback_data="top_refs", icon_custom_emoji_id="5280605017043118832"),
        InlineKeyboardButton(text='Топ по зараб...', callback_data="top_earn", icon_custom_emoji_id="5460709183496171654")
    )
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()


# ==========================================
# АДМИНКА
# ==========================================
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Спонсоры (ОП)", callback_data="bh_menu"),
         InlineKeyboardButton(text="📋 Заявки", callback_data="wd_list")],
        [InlineKeyboardButton(text="🎛 Приватка", callback_data="priv_menu"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🎯 Задания (Сервисы)", callback_data="tasks_menu")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_menu"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="📊 Реклама", callback_data="ad_menu"),
         InlineKeyboardButton(text="💸 Начислить", callback_data="give_start")],
        [InlineKeyboardButton(text="👑 Админы", callback_data="admins_menu"),
         InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_notify")],
        [InlineKeyboardButton(text="👥 Юзер", callback_data="user_find"),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📦 Бэкап", callback_data="backup_help")],
    ])


# ==========================================
# ЭКРАН "АДМИНЫ"
# ==========================================
def admins_list_kb(admins):
    """
    admins — список словарей:
    {"user_id": int, "username": str|None, "is_main": bool}
    Главный админ помечается 👑 и без кнопки удаления.
    """
    builder = InlineKeyboardBuilder()
    for a in admins:
        if a["is_main"]:
            label = f"👑 @{a['username']}" if a["username"] else f"👑 {a['user_id']}"
            builder.row(InlineKeyboardButton(
                text=label,
                callback_data="admin_noop"
            ))
        else:
            label = f"🗑 @{a['username']}" if a["username"] else f"🗑 {a['user_id']}"
            builder.row(InlineKeyboardButton(
                text=label,
                callback_data=f"admin_del:{a['user_id']}",
                style="danger"
            ))
    builder.row(InlineKeyboardButton(
        text="➕ Добавить админа",
        callback_data="admin_add",
        style="success"
    ))
    builder.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="admin_back"
    ))
    return builder.as_markup()


def admin_confirm_delete_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_del_ok:{user_id}", style="danger"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="admins_menu")],
    ])


# ==========================================
# ЮЗЕР
# ==========================================
def user_action_kb(uid: int, is_banned: int):
    builder = InlineKeyboardBuilder()
    ban_text = "✅ Разбанить" if is_banned else "🚫 Забанить"
    builder.row(InlineKeyboardButton(text=ban_text, callback_data=f"u_ban:{uid}", style="danger" if not is_banned else "success"))
    builder.row(InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"u_bal:{uid}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()


# ==========================================
# ЗАЯВКИ НА ВЫВОД
# ==========================================
def wd_page_kb(wid, idx, total):
    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"wd_page:{idx-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data="wd_noop"))
    if idx < total - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"wd_page:{idx+1}"))
    return InlineKeyboardMarkup(inline_keyboard=[
        nav_row,
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}")],
        [InlineKeyboardButton(text="✅✅ Принять все", callback_data="wd_accept_all"),
         InlineKeyboardButton(text="❌❌ Отклонить все", callback_data="wd_reject_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def wd_empty_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]])


def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]])


# ==========================================
# ОП (BOTOHUB) НАСТРОЙКИ
# ==========================================
def bh_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст сообщения", callback_data="bh_edit_text"),
         InlineKeyboardButton(text="📥 ОП на входе (кол-во)", callback_data="bh_edit_entry")],
        [InlineKeyboardButton(text=status, callback_data="bh_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ==========================================
# ПРОМОКОДЫ
# ==========================================
def promos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create")],
        [InlineKeyboardButton(text="📜 Список промокодов", callback_data="promo_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def promo_srv_kb(selected_services):
    builder = InlineKeyboardBuilder()
    services = ['botohub', 'piarflow', 'tgrass', 'trafsly', 'subgram', 'flyer']
    for srv in services:
        status = "✅ " if srv in selected_services else "❌ "
        builder.row(InlineKeyboardButton(text=f"{status}{srv.upper()}", callback_data=f"psrv:{srv}"))
    builder.row(InlineKeyboardButton(text="Готово ➡️", callback_data="psrv_done", style="success"))
    return builder.as_markup()


# ==========================================
# РЕКЛАМА
# ==========================================
def ad_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить метку", callback_data="ad_add")],
        [InlineKeyboardButton(text="📜 Список меток", callback_data="ad_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ==========================================
# НАСТРОЙКИ
# ==========================================
def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Бонус за реферала", callback_data="set:ref_bonus")],
        [InlineKeyboardButton(text="🎯 Бонус за задание", callback_data="set:task_reward")],
        [InlineKeyboardButton(text="👥 Друзей для вывода", callback_data="set:withdraw_friends_required")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])
