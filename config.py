import os

# ==========================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ==========================================
BOT_TOKEN = "8944743132:AAE5QUA4qMduCTmQM2FgLYJmBBlTsmaNcXg" # Токен от @MilingCows_bot
ADMIN_ID = 8742164697
DB = "/app/data/cows.db" # Отдельная база для нового бота

# ==========================================
# СЕРВИСЫ И КЛЮЧИ
# ==========================================
# ОП (Обязательная подписка)
BOTOHUB_TOKEN = "1196d848-7318-4c55-a643-bc0d2e709525"
BOTOHUB_URL = "https://botohub.me/get-tasks-extended"

# Задания (PiarFlow, Tgrass, Trafsly)
PIARFLOW_TOKEN = "XDTTx_U9OEaSruxOOA4C1l1I8rPIKHQ1"
PIARFLOW_URL = "https://piarflow.com/v1"

TGRASS_TOKEN = "5237b312a8ea4d6a8f34ebcb8f3fb4c9"
TGRASS_URL = "https://tgrass.space/tasks"

TRAFSLY_TOKEN = "at_a16dc68b3b6506a4c9486a4c7bbcbc1c"
TRAFSLY_URL = "https://api.trafsly.com/api/v1/get-sponsors"

# ==========================================
# НАСТРОЙКИ ЭКОНОМИКИ
# ==========================================
WITHDRAW_AMOUNTS = [15, 25, 50, 100]
REFERRAL_DAYS = 7

# ==========================================
# ТЕКСТЫ И ПРЕМ-ЭМОДЗИ (DEFAULTS)
# ==========================================
DEFAULTS = {
    # --- Настройки ---
    "ref_bonus": "11",
    "daily_bonus": "1",
    "welcome_bonus": "15",
    "withdraw_friends_required": "3",
    "task_reward": "0.45",
    "welcome_text": "Главное меню 👇",
    
    # Вкл/Выкл сервисов (1 - вкл, 0 - выкл)
    "botohub_enabled": "1",
    "piarflow_enabled": "1",
    "tgrass_enabled": "1",
    "trafsly_enabled": "1",

    # --- Тексты ---
    "menu_text": (
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> Получи свою личную ссылку — жми «Рефералы»\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Приглашай друзей — {ref_bonus} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji> за каждого приглашённого друга!'
    ),
    "ref_text": (
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> <b>Зарабатывай звёзды, приглашая друзей по своей реферальной ссылке</b>\n\n'
        '├ За приглашённого друга — <b>{ref_bonus} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji></b>\n'
        '├ Друг должен перейти по твоей ссылке\n'
        '└ И пройти обязательную подписку (ОП)\n\n'
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> <b>Твоя ссылка:</b>\n'
        '{ref_link}\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Всего приглашено: <b>{total_refs}</b>\n'
        '<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> Засчитано: <b>{confirmed_refs}</b>\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> <b>Кто пришёл по твоей ссылке:</b>\n'
        '{ref_list}\n\n'
        '<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Баланс: <b>{balance}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n\n'
        '<tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> <i>Награда начисляется только после прохождения ОП.</i>'
    ),
    "profile_text": (
        '<tg-emoji emoji-id="5936017305585586269">🪪</tg-emoji> <b>Профиль</b>\n\n'
        'Ник: {username}\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Друзей приглашено: <b>{total_refs}</b>\n'
        '<tg-emoji emoji-id="5460709183496171654">🏆</tg-emoji> Заработано: <b>{total_earned}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        '<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Баланс: <b>{balance}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        'ID: <code>{user_id}</code>\n'
        'Заданий выполнено: <b>{tasks_completed}</b>'
    ),
    "withdraw_text": (
        '<tg-emoji emoji-id="5469744063815102906">💫</tg-emoji> <b>Вывод звезд</b>\n\n'
        'Баланс: <b>{balance}</b> <tg-emoji emoji-id="5417924076503062111">💰</tg-emoji>\n\n'
        'Суммы: {amounts}.\n\n'
        'Срок вывода: 5 минут — 24 часа.\n\n'
        '<i>Напиши сумму.</i>'
    ),
    "instruction_text": (
        '<tg-emoji emoji-id="6030563507299160824">❗️</tg-emoji> <b>Инструкция</b>\n\n'
        '— Не получается набрать минимальную сумму для вывода?\n\n'
        'Делитесь ссылкой не только с друзьями — размещайте её в чатах, своём Telegram-канале, комментариях в TikTok.\n\n'
        '— Поставил/а запрос на вывод, звёзды списались, но не пришли?\n\n'
        'Это нормально — заявка ожидает подтверждения администратора.'
    ),
    "stats_text": (
        '<tg-emoji emoji-id="5334544901428229844">ℹ️</tg-emoji> <b>Информация</b>\n\n'
        '<tg-emoji emoji-id="5255919434811339742">💫</tg-emoji> Старт бота: <b>18.10.2026</b>\n\n'
        '<tg-emoji emoji-id="6032609071373226027">👥</tg-emoji> Всего пользователей: <b>{total_users}</b>\n\n'
        '<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> Всего выплачено: <b>{total_withdrawn}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>'
    ),
    "task_text": (
        '<tg-emoji emoji-id="5422439311196834318">💡</tg-emoji> <b>Получай Звёзды за простые задания!</b> <tg-emoji emoji-id="5470177992950946662">👇</tg-emoji>\n\n'
        '<tg-emoji emoji-id="5416081784641168838">🟢</tg-emoji> Подпишись и нажми «Подтвердить»\n\n'
        'Вознаграждение: +<b>0.45</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>'
    ),
    "sub_text": (
        '<tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> <b>Подпишись, чтобы продолжить</b>\n\n'
        '├ {channel_name}\n\n'
        'Потом жми «Проверить» <tg-emoji emoji-id="5411197345968701560">✅</tg-emoji>'
    ),

    # --- Приватка ---
    "priv_enabled": "0",
    "priv_text": "",
    "priv_buttons": ""
}
