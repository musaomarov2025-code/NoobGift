# keyboards.py
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS

# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================
def main_menu_kb():
    builder = InlineKeyboardBuilder()
    
    # 1-й ряд: Заработать (СИНЯЯ)
    builder.row(InlineKeyboardButton(
        text='Заработать звезды', 
        callback_data="menu_earn",
        icon_custom_emoji_id="6005661956931850799",
        style="primary" # Синяя
    ))
    
    # 2-й ряд: Рефералы / Профиль
    builder.row(
        InlineKeyboardButton(text='Рефералы', callback_data="menu_refs", icon_custom_emoji_id="5278467510604160626"),
        InlineKeyboardButton(text='Профиль', callback_data="menu_profile", icon_custom_emoji_id="5258011929993026890")
    )
    
    # 3-й ряд: Вывод / Статистика
    builder.row(
        InlineKeyboardButton(text='Вывод', callback_data="menu_withdraw", icon_custom_emoji_id="6037408065966312773"),
        InlineKeyboardButton(text='Статистика', callback_data="menu_stats", icon_custom_emoji_id="6154657967317717391")
    )
    
    # 4-й ряд: Инструкция
    builder.row(InlineKeyboardButton(
        text='Инструкция', 
        callback_data="menu_instruction",
        icon_custom_emoji_id="5334544901428229844"
    ))
    
    return builder.as_markup()

# ==========================================
# КНОПКА НАЗАД
# ==========================================
def back_kb(target="menu_back"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Назад', 
        callback_data=target,
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()

# ==========================================
# ЗАДАНИЯ И ОП
# ==========================================
def sub_check_kb(channel_link, channel_name): # <--- ИСПРАВЛЕНО ЗДЕСЬ
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f'Перейти в {channel_name}', 
        url=channel_link,
        icon_custom_emoji_id="5472033358693280429", # Собачка
        style="primary" # Синяя
    ))
    builder.row(InlineKeyboardButton(
        text='Проверить', 
        callback_data="check_sub",
        icon_custom_emoji_id="5411197345968701560", # Галочка
        style="success" # Зеленая
    ))
    return builder.as_markup()

def task_kb(task_url):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Сделать задание', 
        url=task_url,
        icon_custom_emoji_id="5472033358693280429", # Собачка
        style="primary" # Синяя
    ))
    builder.row(
        InlineKeyboardButton(
            text='Проверить', 
            callback_data="check_task", 
            icon_custom_emoji_id="5251503375207392582",
            style="success"
        ),
        InlineKeyboardButton(
            text='Пропустить', 
            callback_data="skip_task",
            icon_custom_emoji_id="6311812139233316820",
            style="danger"
        )
    )
    builder.row(InlineKeyboardButton(
        text='Назад', 
        callback_data="menu_back",
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()

# ==========================================
# ВЫВОД СРЕДСТВ
# ==========================================
def withdraw_kb():
    builder = InlineKeyboardBuilder()
    row_buttons = []
    for amount in WITHDRAW_AMOUNTS:
        row_buttons.append(InlineKeyboardButton(
            text=str(amount), 
            callback_data=f"wd_{amount}",
            style="primary" # Синие кнопки для сумм
        ))
    builder.row(*row_buttons)
    
    builder.row(InlineKeyboardButton(
        text='Назад', 
        callback_data="menu_back",
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()

# ==========================================
# СТАТИСТИКА (ТОПЫ)
# ==========================================
def stats_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='Топ по балансу', 
        callback_data="top_balance",
        icon_custom_emoji_id="5417924076503062111",
        style="primary"
    ))
    builder.row(
        InlineKeyboardButton(text='Топ по реф...', callback_data="top_refs", icon_custom_emoji_id="5280605017043118832"),
        InlineKeyboardButton(text='Топ по зараб...', callback_data="top_earn", icon_custom_emoji_id="5460709183496171654")
    )
    builder.row(InlineKeyboardButton(
        text='Назад', 
        callback_data="menu_back",
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()

def top_period_kb(top_type, current_period="all"):
    builder = InlineKeyboardBuilder()
    periods = [("today", "Сегодня"), ("week", "Неделя"), ("all", "Всё время")]
    row_filters = []
    for p_code, p_name in periods:
        check = " ✓" if current_period == p_code else ""
        row_filters.append(InlineKeyboardButton(
            text=f"{p_name}{check}", 
            callback_data=f"period_{top_type}_{p_code}",
            style="primary" if current_period == p_code else None
        ))
    builder.row(*row_filters)
    
    builder.row(
        InlineKeyboardButton(text='Баланс', callback_data="top_balance", icon_custom_emoji_id="5417924076503062111"),
        InlineKeyboardButton(text='Рефер...', callback_data="top_refs", icon_custom_emoji_id="5280605017043118832"),
        InlineKeyboardButton(text='Зараб...', callback_data="top_earn", icon_custom_emoji_id="5460709183496171654")
    )
    builder.row(InlineKeyboardButton(
        text='Назад', 
        callback_data="menu_stats",
        icon_custom_emoji_id="5346230992044574063"
    ))
    return builder.as_markup()

# ==========================================
# АДМИН ПАНЕЛЬ (Кнопки, если понадобятся)
# ==========================================
def admin_back_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()
