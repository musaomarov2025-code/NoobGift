from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

SERVICES = {"botohub": "Botohub", "tgrass": "Tgrass", "traffy": "Traffy", "trafsly": "Trafsly", "piarflow": "PiarFlow"}

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐️ Заработать Звезды")],
            [KeyboardButton(text="👥 Рефералы"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="💸 Вывод"), KeyboardButton(text="📊 Статистика")],
        ], resize_keyboard=True)

def ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start={user_id}"

from aiogram.types import CopyTextButton

def referral_kb(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    link = ref_link(bot_username, user_id)
    share_url = f"https://t.me/share/url?url={link}&text=Заходи в бота, тут раздают звёзды ⭐️"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Отправить ссылку друзьям", url=share_url)],
        [InlineKeyboardButton(
            text="📋 Скопировать ссылку", 
            copy_text=CopyTextButton(text=link)
        )],
    ])

def tasks_finished_kb(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    link = ref_link(bot_username, user_id)
    share_url = f"https://t.me/share/url?url={link}&text=Заходи в бота, тут раздают звёзды ⭐️"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пригласить друзей", url=share_url)],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_menu")]
    ])

def withdraw_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15 ⭐️", callback_data="withdraw_15"), InlineKeyboardButton(text="25 ⭐️", callback_data="withdraw_25")],
        [InlineKeyboardButton(text="50 ⭐️", callback_data="withdraw_50"), InlineKeyboardButton(text="100 ⭐️", callback_data="withdraw_100")],
    ])

def task_kb(subscribe_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=subscribe_url)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="task_check")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="task_skip")],
    ])

def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Заработать Звезды", callback_data="go_earn")]
    ])

def tasks_finished_kb(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    link = ref_link(bot_username, user_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пригласить друзей", switch_inline_query=f"🎁 Заходи в бота, тут раздают звёзды ⭐️\n\n{link}")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_menu")]
    ])

# --- АДМИН ---
def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. 🤝 Спонсоры", callback_data="adm_services"), InlineKeyboardButton(text="2. 📋 Заявки", callback_data="adm_withdrawals")],
        [InlineKeyboardButton(text="3. 👋 Приветка", callback_data="adm_greeting"), InlineKeyboardButton(text="4. 📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="5. 📨 Рассылка", callback_data="adm_broadcast"), InlineKeyboardButton(text="6. 🎟 Промокоды", callback_data="adm_promos")],
        [InlineKeyboardButton(text="7. 📢 Реклама", callback_data="adm_ads"), InlineKeyboardButton(text="8. ⚙️ Настройки", callback_data="adm_settings")],
        [InlineKeyboardButton(text="9. 👤 Юзер", callback_data="adm_user"), InlineKeyboardButton(text="10. 💾 Бэкап", callback_data="adm_backup")],
    ])

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")]])

def admin_services_kb(services_enabled: dict) -> InlineKeyboardMarkup:
    rows = []
    for key, label in SERVICES.items():
        status = "🟢 Вкл" if services_enabled.get(key) else "🔴 Выкл"
        rows.append([InlineKeyboardButton(text=f"{label} — {status}", callback_data=f"adm_svc_toggle_{key}")])
    rows.append([InlineKeyboardButton(text="🔑 API-ключи", callback_data="adm_svc_keys")])
    rows.append([InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_services_keys_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"adm_key_edit_{key}")] for key, label in SERVICES.items()]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm_services")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_greeting_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="adm_greet_text")],
        [InlineKeyboardButton(text="🖼 Добавить/изменить медиа", callback_data="adm_greet_media")],
        [InlineKeyboardButton(text="🔘 Добавить кнопку", callback_data="adm_greet_button")],
        [InlineKeyboardButton(text="🗑 Очистить кнопки", callback_data="adm_greet_clear")],
        [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")],
    ])

def admin_withdraw_card_kb(wid: int, index: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    if total > 1:
        rows.append([InlineKeyboardButton(text="◀️", callback_data=f"adm_wd_nav_{(index - 1) if index > 0 else total - 1}"), InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"), InlineKeyboardButton(text="▶️", callback_data=f"adm_wd_nav_{(index + 1) % total}")])
    rows.append([InlineKeyboardButton(text="✅ Принять", callback_data=f"adm_wd_accept_{wid}"), InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_wd_reject_{wid}")])
    rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"adm_wd_skip_{wid}")])
    rows.append([InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_promos_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm_promo_create")], [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")]])

def admin_ads_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Создать рекламу", callback_data="adm_ad_create")], [InlineKeyboardButton(text="📋 Список реклам", callback_data="adm_ad_list")], [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")]])

def admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 % с рефералов", callback_data="adm_set_ref_percent")],
        [InlineKeyboardButton(text="⭐️ Цена за задание", callback_data="adm_set_task_reward")],
        [InlineKeyboardButton(text="📢 Канал заявок", callback_data="adm_set_withdraw_channel")],
        [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")],
    ])

def admin_backup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📤 Скачать бэкап", callback_data="adm_backup_download")], [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")]])

def admin_user_kb(uid: int, is_banned: bool) -> InlineKeyboardMarkup:
    ban_text = "🔓 Разблокировать" if is_banned else "🚫 Заблокировать"
    ban_cb = f"usr_unban_{uid}" if is_banned else f"usr_ban_{uid}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Начислить", callback_data=f"usr_bal_plus_{uid}"), InlineKeyboardButton(text="➖ Списать", callback_data=f"usr_bal_minus_{uid}")],
        [InlineKeyboardButton(text=ban_text, callback_data=ban_cb)],
        [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")],
    ])
