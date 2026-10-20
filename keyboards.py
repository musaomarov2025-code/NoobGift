from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS

# ==========================================
# ГЛАВНОЕ МЕНЮ
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
    builder.row(InlineKeyboardButton(text='Назад', callback_data=target, icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()

# ==========================================
# ЗАДАНИЯ И ОП
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
    builder.row(InlineKeyboardButton(text='Сделать задание', url=task_url, icon_custom_emoji_id="5472033358693280429", style="primary"))
    builder.row(
        InlineKeyboardButton(text='Проверить', callback_data="check_task", icon_custom_emoji_id="5251503375207392582", style="success"),
        InlineKeyboardButton(text='Пропустить', callback_data="skip_task", icon_custom_emoji_id="6311812139233316820", style="danger")
    )
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()

# ==========================================
# ВЫВОД И СТАТИСТИКА
# ==========================================
def withdraw_kb():
    builder = InlineKeyboardBuilder()
    row_buttons = []
    for amount in WITHDRAW_AMOUNTS:
        row_buttons.append(InlineKeyboardButton(text=str(amount), callback_data=f"wd_{amount}", style="primary"))
    builder.row(*row_buttons)
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()

def stats_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back", icon_custom_emoji_id="5346230992044574063"))
    return builder.as_markup()

# ==========================================
# АДМИНКА
# ==========================================
def admin_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔌 Интеграции", callback_data="admin_integrations"),
        InlineKeyboardButton(text="👤 Поиск юзера", callback_data="admin_find_user")
    )
    builder.row(
        InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promos"),
        InlineKeyboardButton(text="📊 Реклама", callback_data="admin_ads")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="💾 Бэкап", callback_data="admin_backup")
    )
    return builder.as_markup()

def back_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()

def user_action_kb(uid, is_banned):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Изменить баланс", callback_data=f"u_bal:{uid}"))
    ban_text = "✅ Разбанить" if is_banned else "🚫 Забанить"
    builder.row(InlineKeyboardButton(text=ban_text, callback_data=f"u_ban:{uid}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()
