# keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS

# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================
def main_menu_kb():
    builder = InlineKeyboardBuilder()
    
    # 1-й ряд: Заработать
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="6005661956931850799">⭐️</tg-emoji> Заработать звезды', 
        callback_data="menu_earn"
    ))
    
    # 2-й ряд: Рефералы / Профиль
    builder.row(
        InlineKeyboardButton(text='<tg-emoji emoji-id="5278467510604160626">💰</tg-emoji> Рефералы', callback_data="menu_refs"),
        InlineKeyboardButton(text='<tg-emoji emoji-id="5258011929993026890">👤</tg-emoji> Профиль', callback_data="menu_profile")
    )
    
    # 3-й ряд: Вывод / Статистика
    builder.row(
        InlineKeyboardButton(text='<tg-emoji emoji-id="6037408065966312773">🤑</tg-emoji> Вывод', callback_data="menu_withdraw"),
        InlineKeyboardButton(text='<tg-emoji emoji-id="6154657967317717391">↗️</tg-emoji> Статистика', callback_data="menu_stats")
    )
    
    # 4-й ряд: Инструкция
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5334544901428229844">ℹ️</tg-emoji> Инструкция', 
        callback_data="menu_instruction"
    ))
    
    return builder.as_markup()

# ==========================================
# КНОПКА НАЗАД (используется везде)
# ==========================================
def back_kb(target="main_menu"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5346230992044574063">⬅️</tg-emoji> Назад', 
        callback_data=target
    ))
    return builder.as_markup()

# ==========================================
# ЗАДАНИЯ (ОП на входе и Сами задания)
# ==========================================
def sub_check_kb(channel_link):
    builder = InlineKeyboardBuilder()
    # Кнопка на подписку
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="6311812139233316820">🤝</tg-emoji> Подписаться',
        url=channel_link
    ))
    # Кнопка проверки
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> Проверить',
        callback_data="check_sub"
    ))
    return builder.as_markup()

def task_kb(task_url):
    builder = InlineKeyboardBuilder()
    # Кнопка перехода
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="6311812139233316820">🤝</tg-emoji> Сделать задание',
        url=task_url
    ))
    # Кнопки Проверить / Пропустить
    builder.row(
        InlineKeyboardButton(text='<tg-emoji emoji-id="5251503375207392582">✅</tg-emoji> Проверить', callback_data="check_task"),
        InlineKeyboardButton(text='SKIP Пропустить', callback_data="skip_task")
    )
    # Кнопка Назад
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5346230992044574063">⬅️</tg-emoji> Назад',
        callback_data="menu_back"
    ))
    return builder.as_markup()

# ==========================================
# ВЫВОД СРЕДСТВ
# ==========================================
def withdraw_kb():
    builder = InlineKeyboardBuilder()
    
    # Кнопки с суммами (в один ряд)
    row_buttons = []
    for amount in WITHDRAW_AMOUNTS:
        row_buttons.append(InlineKeyboardButton(text=str(amount), callback_data=f"wd_{amount}"))
    builder.row(*row_buttons)
    
    # Кнопка Назад
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5346230992044574063">⬅️</tg-emoji> Назад',
        callback_data="menu_back"
    ))
    return builder.as_markup()

# ==========================================
# СТАТИСТИКА (ТОПЫ)
# ==========================================
def stats_kb():
    builder = InlineKeyboardBuilder()
    
    # Кнопки топов
    builder.row(InlineKeyboardButton(text='<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Топ по балансу', callback_data="top_balance"))
    builder.row(
        InlineKeyboardButton(text='<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Топ по реф...', callback_data="top_refs"),
        InlineKeyboardButton(text='<tg-emoji emoji-id="5460709183496171654">🏆</tg-emoji> Топ по зараб...', callback_data="top_earn")
    )
    
    # Кнопка Назад
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5346230992044574063">⬅️</tg-emoji> Назад',
        callback_data="menu_back"
    ))
    return builder.as_markup()

def top_period_kb(top_type, current_period="all"):
    builder = InlineKeyboardBuilder()
    
    # Фильтры времени
    periods = [
        ("today", "Сегодня"),
        ("week", "Неделя"),
        ("all", "Всё время")
    ]
    
    row_filters = []
    for p_code, p_name in periods:
        check = " ✓" if current_period == p_code else ""
        row_filters.append(InlineKeyboardButton(text=f"{p_name}{check}", callback_data=f"period_{top_type}_{p_code}"))
    builder.row(*row_filters)
    
    # Переключение между топами
    builder.row(
        InlineKeyboardButton(text='💰 Баланс', callback_data="top_balance"),
        InlineKeyboardButton(text='👥 Рефер...', callback_data="top_refs"),
        InlineKeyboardButton(text='🏆 Зараб...', callback_data="top_earn")
    )
    
    # Кнопка Назад
    builder.row(InlineKeyboardButton(
        text='<tg-emoji emoji-id="5346230992044574063">⬅️</tg-emoji> Назад',
        callback_data="menu_stats"
    ))
    return builder.as_markup()
