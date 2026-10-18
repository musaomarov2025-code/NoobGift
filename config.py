import os

BOT_TOKEN = "СЮДА_ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER"
ADMIN_ID = 8742164697
DB = "/app/data/cows.db"

# === ОП (Botohub) ===
BOTOHUB_TOKEN = "1196d848-7318-4c55-a643-bc0d2e709525"
BOTOHUB_URL = "https://botohub.me/get-tasks-extended"

# === Задания (3 сервиса) ===
PIARFLOW_TOKEN = "XDTTx_U9OEaSruxOOA4C1l1I8rPIKHQ1"
PIARFLOW_URL = "https://piarflow.com/v1"

TGRASS_TOKEN = "5237b312a8ea4d6a8f34ebcb8f3fb4c9"
TGRASS_URL = "https://tgrass.space/tasks"

TRAFSLY_TOKEN = "at_a16dc68b3b6506a4c9486a4c7bbcbc1c"
TRAFSLY_URL = "https://api.trafsly.com/api/v1/get-sponsors"

REFERRAL_DAYS = 7
REFERRAL_REMIND_MIN = 3
JOIN_REQUEST_HOURS = 24

WITHDRAW_AMOUNTS = [15, 25, 50, 100]

DEFAULTS = {
    "ref_bonus": "11",
    "daily_bonus": "1",
    "welcome_bonus": "15",
    "withdraw_friends_required": "3",
    "task_reward": "0.45",
    "welcome_text": "Главное меню 👇",
    "withdraw_video_id": "",
    
    "botohub_enabled": "1",
    "botohub_entry_count": "2",
    "botohub_text": (
        '<tg-emoji emoji-id="5258093637450866522">🔒</tg-emoji> Для использования бота подпишись на каналы ниже\n\n'
        '<tg-emoji emoji-id="6026034017608930629">👉</tg-emoji> После подписки нажимай на кнопку '
        '"<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> Я Подписался"'
    ),

    "piarflow_enabled": "1",
    "tgrass_enabled": "1",
    "trafsly_enabled": "1",

    "menu_text": (
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> Получи свою личную ссылку — жми «Рефералы»\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Приглашай друзей — {ref_bonus} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji> за каждого приглашённого друга!'
    ),
    "ref_text": (
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> <b>Зарабатывай звёзды, приглашая друзей</b>\n\n'
        '├ За друга — <b>{ref_bonus} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji></b>\n'
        '└ Друг должен пройти ОП\n\n'
        '<b>Твоя ссылка:</b>\n{ref_link}\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Всего: <b>{total_refs}</b>\n'
        '<tg-emoji emoji-id="5411197345968701560">✅</tg-emoji> Засчитано: <b>{confirmed_refs}</b>\n\n'
        '<b>Кто пришёл:</b>\n{ref_list}\n\n'
        '<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Баланс: <b>{balance}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>'
    ),
    "profile_text": (
        '<tg-emoji emoji-id="5936017305585586269">🪪</tg-emoji> <b>Профиль</b>\n\n'
        'Ник: {username}\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Друзей: <b>{total_refs}</b>\n'
        '<tg-emoji emoji-id="5460709183496171654">🏆</tg-emoji> Заработано: <b>{total_earned}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        '<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Баланс: <b>{balance}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        'ID: <code>{user_id}</code>\n'
        'Заданий: <b>{tasks_completed}</b>'
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
        '— Не получается набрать сумму для вывода?\n\n'
        'Делитесь ссылкой в чатах, каналах, TikTok.\n\n'
        '— Звёзды списались, но не пришли?\n\n'
        'Заявка ожидает подтверждения администратора.'
    ),
    "stats_text": (
        '<tg-emoji emoji-id="5334544901428229844">ℹ️</tg-emoji> <b>Информация</b>\n\n'
        '<tg-emoji emoji-id="5255919434811339742">💫</tg-emoji> Старт: <b>18.10.2026</b>\n\n'
        '<tg-emoji emoji-id="6032609071373226027">👥</tg-emoji> Всего юзеров: <b>{total_users}</b>\n\n'
        '<tg-emoji emoji-id="4958926882994127612">💰</tg-emoji> Выплачено: <b>{total_withdrawn}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>'
    ),
    "task_text": (
        '<tg-emoji emoji-id="5422439311196834318">💡</tg-emoji> <b>Получай Звёзды за простые задания!</b> <tg-emoji emoji-id="5470177992950946662">👇</tg-emoji>\n\n'
        '<tg-emoji emoji-id="5416081784641168838">🟢</tg-emoji> Подпишись и нажми «Подтвердить»\n\n'
        'Вознаграждение: +<b>{reward}</b> <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>'
    ),
    "priv_enabled": "0",
    "priv_text": "",
    "priv_buttons": ""
}
