from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WITHDRAW_AMOUNTS

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Заработать звезды', icon_custom_emoji_id="6005661956931850799", callback_data="menu_earn", style="primary"))
    builder.row(InlineKeyboardButton(text='Рефералы', icon_custom_emoji_id="5278467510604160626", callback_data="menu_refs"), InlineKeyboardButton(text='Профиль', icon_custom_emoji_id="5258011929993026890", callback_data="menu_profile"))
    builder.row(InlineKeyboardButton(text='Вывод', icon_custom_emoji_id="6037408065966312773", callback_data="menu_withdraw"), InlineKeyboardButton(text='Статистика', icon_custom_emoji_id="6154657967317717391", callback_data="menu_stats"))
    builder.row(InlineKeyboardButton(text='Инструкция', icon_custom_emoji_id="5334544901428229844", callback_data="menu_instruction"))
    return builder.as_markup()

def back_kb(target="menu_back"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Назад', icon_custom_emoji_id="5346230992044574063", callback_data=target))
    return builder.as_markup()

def task_kb(url, task_type="service", tid=None):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Перейти к заданию', icon_custom_emoji_id="5472033358693280429", url=url, style="primary"))
    if task_type == "service":
        builder.row(InlineKeyboardButton(text='Проверить', icon_custom_emoji_id="5251503375207392582", callback_data="check_task", style="success"), InlineKeyboardButton(text='Пропустить', icon_custom_emoji_id="6311812139233316820", callback_data="skip_task", style="danger"))
    elif task_type == "custom":
        builder.row(InlineKeyboardButton(text='Проверить', icon_custom_emoji_id="5251503375207392582", callback_data=f"check_custom:{tid}", style="success"), InlineKeyboardButton(text='Пропустить', icon_custom_emoji_id="6311812139233316820", callback_data="skip_task", style="danger"))
    builder.row(InlineKeyboardButton(text='Назад', icon_custom_emoji_id="5346230992044574063", callback_data="menu_back"))
    return builder.as_markup()

def sponsor_kb(sponsors):
    builder = InlineKeyboardBuilder()
    for s in sponsors:
        name = s['name'] if s['name'] else "Канал"
        url = s['url'] if s['url'] else "https://t.me/telegram"
        builder.row(InlineKeyboardButton(text=name, url=url, style="primary"))
    builder.row(InlineKeyboardButton(text="Проверить", icon_custom_emoji_id="5251503375207392582", callback_data="check_sponsors", style="success"))
    return builder.as_markup()

def withdraw_kb():
    builder = InlineKeyboardBuilder()
    builder.row(*[InlineKeyboardButton(text=str(amt), callback_data=f"wd_{amt}", style="primary") for amt in WITHDRAW_AMOUNTS])
    builder.row(InlineKeyboardButton(text='Назад', icon_custom_emoji_id="5346230992044574063", callback_data="menu_back"))
    return builder.as_markup()

def stats_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text='Топ по балансу', icon_custom_emoji_id="5417924076503062111", callback_data="top_bal", style="primary"))
    builder.row(InlineKeyboardButton(text='Топ по реф...', icon_custom_emoji_id="5280605017043118832", callback_data="top_ref"), InlineKeyboardButton(text='Топ по зараб...', icon_custom_emoji_id="5460709183496171654", callback_data="top_earn"))
    builder.row(InlineKeyboardButton(text='Назад', icon_custom_emoji_id="5346230992044574063", callback_data="menu_back"))
    return builder.as_markup()

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Спонсоры", callback_data="admin_sponsors"), InlineKeyboardButton(text="💼 Свои задания", callback_data="admin_tasks")],
        [InlineKeyboardButton(text="📋 Заявки", callback_data="admin_wd"), InlineKeyboardButton(text="👥 Юзер", callback_data="admin_user")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_notify"), InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"), InlineKeyboardButton(text="📦 Бэкап", callback_data="admin_backup")]
    ])

def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]])

def admin_sponsors_kb(sponsors):
    builder = InlineKeyboardBuilder()
    for s in sponsors:
        name = s['name'] if s['name'] else "Без названия"
        builder.row(InlineKeyboardButton(text=f"🗑 {name}", callback_data=f"sp_del:{s['id']}", style="danger"))
    builder.row(InlineKeyboardButton(text="➕ Добавить спонсора", callback_data="sp_add", style="success"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()

def admin_tasks_kb(tasks):
    builder = InlineKeyboardBuilder()
    for t in tasks:
        name = t['name'] if t['name'] else "Без названия"
        builder.row(InlineKeyboardButton(text=f"🗑 {name} ({t['reward']}⭐)", callback_data=f"task_del:{t['id']}", style="danger"))
    builder.row(InlineKeyboardButton(text="➕ Добавить задание", callback_data="task_add", style="success"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()

def wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}", style="success"), InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}", style="danger")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])

def settings_kb(ref_percent, task_reward, penalty):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"👥 Процент рефереру ({ref_percent}%)", callback_data="set:ref_percent")],
        [InlineKeyboardButton(text=f"🎯 Награда за задание ({task_reward}⭐)", callback_data="set:task_reward")],
        [InlineKeyboardButton(text=f"⚠️ Штраф за отписку ({penalty}⭐)", callback_data="set:sponsor_penalty")],
        [InlineKeyboardButton(text="📝 Текст меню", callback_data="set:menu_text")],
        [InlineKeyboardButton(text="🖼 Аватарка меню", callback_data="set:menu_avatar")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])

def backup_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Скачать файл базы", callback_data="backup_download", style="primary")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]])

def notify_menu_kb(notifs):
    builder = InlineKeyboardBuilder()
    for n in notifs:
        short = n['text'][:15] + "..." if n['text'] else "Медиа"
        builder.row(InlineKeyboardButton(text=f"🗑 {short} ({n['interval_h']}ч)", callback_data=f"notify_del:{n['id']}", style="danger"))
    builder.row(InlineKeyboardButton(text="➕ Создать уведомление", callback_data="notify_add", style="success"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    return builder.as_markup()
