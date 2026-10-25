from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Заработать звезды', callback_data="menu_earn", style="primary"))
    builder.row(
        InlineKeyboardButton(text='Рефералы', callback_data="menu_refs"),
        InlineKeyboardButton(text='Профиль', callback_data="menu_profile")
    )
    builder.row(
        InlineKeyboardButton(text='Вывод', callback_data="menu_withdraw"),
        InlineKeyboardButton(text='Статистика', callback_data="menu_stats")
    )
    return builder.as_markup()

def back_kb(target="menu_back"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Назад', callback_data=target))
    return builder.as_markup()

def task_kb(url):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Перейти к заданию', url=url, style="primary"))
    builder.row(
        InlineKeyboardButton(text='Проверить', callback_data="check_task", style="success"),
        InlineKeyboardButton(text='Пропустить', callback_data="skip_task", style="danger")
    )
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back"))
    return builder.as_markup()

def withdraw_kb():
    builder = InlineKeyboardBuilder()
    builder.row(*[InlineKeyboardButton(text=str(amt), callback_data=f"wd_{amt}", style="primary") for amt in WITHDRAW_AMOUNTS])
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back"))
    return builder.as_markup()

def stats_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Топ по балансу', callback_data="top_bal", style="primary"))
    builder.row(
        InlineKeyboardButton(text='Топ по реф...', callback_data="top_ref"),
        InlineKeyboardButton(text='Топ по зараб...', callback_data="top_earn")
    )
    builder.row(InlineKeyboardButton(text='Назад', callback_data="menu_back"))
    return builder.as_markup()

def sponsor_kb(sponsors):
    builder = InlineKeyboardBuilder()
    for s in sponsors:
        builder.row(InlineKeyboardButton(text=s['name'], url=s['url'], style="primary"))
    builder.row(InlineKeyboardButton(text="Проверить", callback_data="check_sponsors", style="success"))
    return builder.as_markup()

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Мои спонсоры", callback_data="admin_sponsors"), InlineKeyboardButton(text="📋 Заявки", callback_data="admin_wd")],
        [InlineKeyboardButton(text="👥 Юзер", callback_data="admin_user"), InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"), InlineKeyboardButton(text="📦 Бэкап", callback_data="admin_backup")]
    ])
