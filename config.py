import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8742164697").strip())
DB = "/app/data/cows.db"

PIARFLOW_TOKEN = "XDTTx_U9OEaSruxOOA4C1l1I8rPIKHQ1"
PIARFLOW_URL = "https://piarflow.com/v1"
TGRASS_TOKEN = "5237b312a8ea4d6a8f34ebcb8f3fb4c9"
TRAFSLY_TOKEN = "at_a16dc68b3b6506a4c9486a4c7bbcbc1c"

WITHDRAW_AMOUNTS = [15, 25, 50, 100]

DEFAULTS = {
    "ref_percent": "15",
    "task_reward": "1.0",
    "sponsor_penalty": "5.0",
    "menu_avatar": "",
    "instruction_text": "❗️ <b>Инструкция</b>\n\nЗдесь ты можешь зарабатывать звезды, выполняя задания и приглашая друзей.\n\nВыполняй задания, получай % с друзей и выводи звезды!",
    
    "menu_text": (
        '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> Забирай свою ссылку и приглашай друзей!\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Ты получаешь <b>{ref_percent}%</b> с каждого задания друга <b>пожизненно</b>.'
    ),
    "ref_text": (
        '<tg-emoji emoji-id="5372926953978341366">👥</tg-emoji> <b>Реферальная система</b>\n\n'
        'Приглашайте друзей и получайте <b>{ref_percent}%</b> от каждого выполненного ими задания пожизненно!\n\n'
        '<tg-emoji emoji-id="5375129357373165375">🔗</tg-emoji> <b>Ваша личная ссылка:</b>\n'
        '<code>{ref_link}</code>\n\n'
        '<tg-emoji emoji-id="5452122079287589280">📊</tg-emoji> <b>Ваша статистика:</b>\n'
        '• <b>Приглашено друзей:</b> {total_refs} чел.\n'
        '• <b>Доход с друзей:</b> {ref_earnings} <tg-emoji emoji-id="5435957248314579621">⭐️</tg-emoji>'
    ),
    "profile_text": (
        '<tg-emoji emoji-id="5936017305585586269">🪪</tg-emoji> <b>Профиль</b>\n\n'
        'Ник: {username}\n\n'
        '<tg-emoji emoji-id="5280605017043118832">👥</tg-emoji> Друзей приглашено: {total_refs}\n'
        '<tg-emoji emoji-id="5386367538735104399">⌛</tg-emoji> Выведено: {total_withdrawn} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        '<tg-emoji emoji-id="5417924076503062111">💰</tg-emoji> Баланс: {balance} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji>\n'
        'ID: <code>{user_id}</code>\n'
        'Заданий выполнено: {tasks_completed}\n'
        '<b>Заработано с друзей: {ref_earnings} <tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji></b>'
    ),
    "withdraw_text": "💫 <b>Вывод</b>\nБаланс: {balance}⭐\n\nДоступно: {amounts}\n\nНапиши сумму или нажми кнопку.",
    "task_text": "💡 <b>Задание</b>\nНаграда: +{reward}⭐",
    "sponsor_text": "⚠️ <b>Подпишись, чтобы продолжить</b>\n\n{sponsors}\n\nПотом жми «Проверить» ✅"
}
