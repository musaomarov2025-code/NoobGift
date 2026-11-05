from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_for_service_key = State()
    waiting_for_task_reward = State()
    waiting_for_ref_reward = State()
    waiting_for_ref_tasks = State()
    waiting_for_user_search = State()
    waiting_for_new_balance = State()
    broadcast_text = State()
    broadcast_media = State()
    broadcast_buttons = State()
    promo_text = State()
    promo_media = State()
    promo_buttons = State()
    ad_name = State()
    ad_trafer = State()
    ad_owner = State()

def user_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐ Заработать"), KeyboardButton(text="💎 Задания")],
            [KeyboardButton(text="🎁 Вывести")]
        ],
        resize_keyboard=True
    )

def earn_inline_kb(ref_link: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Скопировать ссылку", copy_text=CopyTextButton(text=ref_link)),
            InlineKeyboardButton(text="🔗 Отправить другу", url=f"https://t.me/share/url?url={ref_link}")
        ]
    ])

def task_inline_kb(link: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти", url=link)],
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="task_confirm"),
            InlineKeyboardButton(text="Пропустить", callback_data="task_skip")
        ]
    ])

def withdraw_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15 ⭐", callback_data="wd_15"), InlineKeyboardButton(text="25 ⭐", callback_data="wd_25")],
        [InlineKeyboardButton(text="50 ⭐", callback_data="wd_50"), InlineKeyboardButton(text="100 ⭐", callback_data="wd_100")]
    ])

def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"), InlineKeyboardButton(text="🖼 Показы/Приветка", callback_data="adm_promos")],
        [InlineKeyboardButton(text="📈 Реклама", callback_data="adm_ads"), InlineKeyboardButton(text="👤 Юзер", callback_data="adm_user")],
        [InlineKeyboardButton(text="⚙️ Сервисы", callback_data="adm_services"), InlineKeyboardButton(text="💸 Заявки", callback_data="adm_withdrawals")],
        [InlineKeyboardButton(text="🛠 Настройки", callback_data="adm_settings"), InlineKeyboardButton(text="💾 Бэкап", callback_data="adm_backup")]
    ])

def admin_services_kb(services):
    kb = []
    for s in services:
        status = "🟢" if s['is_active'] else "🔴"
        kb.append([
            InlineKeyboardButton(text=f"{status} {s['name']}", callback_data=f"adm_srv_toggle_{s['id']}"),
            InlineKeyboardButton(text="🔑", callback_data=f"adm_srv_key_{s['id']}"),
            InlineKeyboardButton(text="⬆️", callback_data=f"adm_srv_up_{s['id']}"),
            InlineKeyboardButton(text="⬇️", callback_data=f"adm_srv_down_{s['id']}")
        ])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_withdraw_kb(wd_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_wd_ok_{wd_id}"), InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_wd_no_{wd_id}")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="adm_wd_skip")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])

def admin_user_kb(user_id: int, is_banned: int):
    ban_text = "🔓 Разблокировать" if is_banned else "🚫 Заблокировать"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"adm_usr_bal_{user_id}")],
        [InlineKeyboardButton(text=ban_text, callback_data=f"adm_usr_ban_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])

def admin_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Награда за задание", callback_data="adm_set_task")],
        [InlineKeyboardButton(text="Награда за реферала", callback_data="adm_set_ref")],
        [InlineKeyboardButton(text="Заданий для реферала", callback_data="adm_set_reftasks")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])

def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="adm_back")]
    ])

def admin_broadcast_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data="adm_bc_text"), InlineKeyboardButton(text="📷 Медиа", callback_data="adm_bc_media")],
        [InlineKeyboardButton(text="🔗 Кнопки", callback_data="adm_bc_buttons")],
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="adm_bc_preview"), InlineKeyboardButton(text="🚀 Отправить", callback_data="adm_bc_send")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_bc_delete"), InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])

def admin_promos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👋 Изменить приветку", callback_data="adm_promo_welcome")],
        [InlineKeyboardButton(text="➕ Добавить показ", callback_data="adm_promo_add_show")],
        [InlineKeyboardButton(text="📋 Список показов", callback_data="adm_promo_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])

def admin_promo_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data="adm_pr_menu_text"), InlineKeyboardButton(text="📷 Медиа/Стикер", callback_data="adm_pr_menu_media")],
        [InlineKeyboardButton(text="🔗 Кнопки", callback_data="adm_pr_menu_buttons")],
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="adm_pr_menu_preview"), InlineKeyboardButton(text="💾 Сохранить", callback_data="adm_pr_menu_save")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_pr_menu_clear"), InlineKeyboardButton(text="◀️ Отмена", callback_data="adm_promos")]
    ])

def admin_ads_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить трафера", callback_data="adm_ad_add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])
