# Здесь — статические тексты и шаблоны.
# Приветствие хранится в БД и редактируется через админку (см. database.get_greeting).

STAR_MESSAGE = "⭐️"
MENU_TEXT = "📋 <b>Главное меню</b>\n\nВыбери действие:"

DEFAULT_GREETING = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "⭐️ Здесь ты зарабатываешь Telegram Stars, выполняя простые задания.\n"
    "👥 Приглашай друзей и получай % с их заработка.\n"
    "💎 Выводи звёзды прямо в Telegram."
)


# ============= ПРОФИЛЬ =============

def profile_text(user: dict) -> str:
    return (
        "👤 <b>Личный кабинет</b>\n\n"
        f"🆔 Ваш ID: <code>{user['user_id']}</code>\n"
        f"⭐️ Доступный баланс: {user['balance']:.2f} Stars\n"
        f"⏳ В холде (до 24 часов): {user['hold']:.2f} Stars\n"
        f"💎 Всего выведено: {user['total_withdrawn']:.2f} Stars\n"
        f"✅ Выполнено заданий: {user['tasks_done']}\n"
        f"👥 Рефералов: {user['refs_count']} чел. "
        f"(принесли: {user['refs_earned']:.2f} ⭐️)"
    )


# ============= РЕФЕРАЛЫ =============

def referrals_text(bot_username: str, user: dict) -> str:
    link = f"https://t.me/{bot_username}?start={user['user_id']}"
    return (
        "👥 <b>Реферальная система</b>\n\n"
        "Приглашайте друзей и получайте % от каждого выполненного ими задания пожизненно!\n\n"
        f"🔗 Ваша личная ссылка:\n<code>{link}</code>\n\n"
        "📊 <b>Ваша статистика:</b>\n"
        f"• Приглашено друзей: {user['refs_count']} чел.\n"
        f"• Доход с друзей: {user['refs_earned']:.2f} ⭐️"
    )


# ============= ВЫВОД =============

def withdraw_text(user: dict) -> str:
    return (
        "💎 <b>Вывод Telegram Stars</b>\n\n"
        f"💰 Ваш баланс: {user['balance']:.2f} ⭐️\n\n"
        "Выберите сумму для вывода. Обязательно убедитесь, "
        "что у вас установлен @username в профиле Telegram:"
    )


def withdrawal_created_text(wid: int, amount: float) -> str:
    return (
        f"✅ Заявка #{wid} на {amount:.2f} ⭐️ создана.\n\n"
        "Срок вывода: 5 минут — 24 часа."
    )


def withdrawal_channel_new_text(wid: int, username: str, user_id: int, amount: float) -> str:
    who = f"@{username}" if username else f"{user_id}"
    return (
        "⌛️ <b>Создана заявка на вывод!</b>\n\n"
        f"🆔 Заявка: #{wid}\n"
        f"👤 Пользователь: {who}\n"
        f"⭐️ Количество: {amount:.2f} Звёзд\n\n"
        "👉 @SmilingNoob_bot"
    )


def withdrawal_channel_paid_text(wid: int, username: str, user_id: int, amount: float) -> str:
    who = f"@{username}" if username else f"{user_id}"
    return (
        "✅ <b>Отправлена выплата!</b>\n\n"
        f"🆔 Заявка: #{wid}\n"
        f"👤 Пользователь: {who}\n"
        f"⭐️ Количество: {amount:.2f} Звёзд\n\n"
        "👉 @SmilingNoob_bot"
    )


def withdrawal_channel_reject_text(wid: int, username: str, user_id: int, amount: float) -> str:
    who = f"@{username}" if username else f"{user_id}"
    return (
        "❌ <b>Заявка отклонена</b>\n\n"
        f"🆔 Заявка: #{wid}\n"
        f"👤 Пользователь: {who}\n"
        f"⭐️ Количество: {amount:.2f} Звёзд\n\n"
        "👉 @SmilingNoob_bot"
    )


def withdrawal_rejected_user_text(wid: int, amount: float) -> str:
    return (
        f"❌ Заявка #{wid} на {amount:.2f} ⭐️ отклонена.\n\n"
        "Звёзды возвращены на ваш баланс."
    )


# ============= ЗАДАНИЯ =============

def task_text(index: int, total: int, source: str, sponsor: str, reward: float) -> str:
    return (
        f"📋 <b>Задание {index} из {total}</b>\n\n"
        f"📌 Источник для выполнения: {source}\n"
        f"📢 Для выполнения, перейди по ссылке и подпишись на канал: {sponsor}\n"
        f"⭐ Награда за выполнение: {reward:.2f}\n\n"
        "✅ Для продолжения перейди по ссылке, подпишись на канал, "
        "и нажми на кнопку «Проверить подписку»."
    )


def task_done_toast(reward: float) -> str:
    return f"✅ Задание выполнено! +{reward:.2f} ⭐️ в холд"


TASK_NOT_SUBSCRIBED_TOAST = "❌ Подписка не найдена. Подпишись на канал и попробуй снова."
TASKS_EMPTY_TOAST = "😔 Пока нет доступных заданий. Попробуй позже!"


def tasks_finished_text(balance: float, bot_username: str, user_id: int) -> str:
    link = f"https://t.me/{bot_username}?start={user_id}"
    return (
        "🎉 <b>Молодец! Ты выполнил все доступные задания!</b>\n\n"
        f"💰 Твой баланс: {balance:.2f} Stars\n\n"
        "👥 Не останавливайся! Приглашай друзей и получай процент "
        "с каждого их выполненного задания — пожизненно!\n\n"
        f"🔗 Твоя реф-ссылка:\n<code>{link}</code>"
    )


# ============= ХОЛД / РЕФЕРАЛЫ =============

def hold_released_text(amount: float) -> str:
    return f"🎉 <b>+{amount:.2f} ⭐️</b> переведено из холда на ваш баланс!"


def ref_released_text(amount: float) -> str:
    return f"🎉 <b>+{amount:.2f} ⭐️</b> — доход с вашего реферала переведён на баланс!"


def ref_earned_text(ref_username: str, ref_id: int, amount: float) -> str:
    who = f"@{ref_username}" if ref_username else f"{ref_id}"
    return (
        "🎉 <b>Ваш реферал выполнил задание!</b>\n\n"
        f"👤 Реферал: {who}\n"
        f"💰 Вам начислено: +{amount:.2f} ⭐️ (в холд)"
    )


# ============= СТАТИСТИКА =============

def stats_text(stats: dict, top_users: list) -> str:
    earned = stats.get("hold_total", 0) + stats.get("withdrawn_total", 0)
    text = (
        "📊 <b>Общая статистика проекта</b>\n\n"
        f"👥 Всего участников: {stats.get('total_users', 0)} чел.\n"
        f"🆕 Новых за сегодня: +{stats.get('new_today', 0)} чел.\n"
        f"✅ Выполнено заданий: {stats.get('tasks_done_total', 0)} шт.\n"
        f"⭐️ Заработано участниками: {earned:.2f} Stars\n"
        f"⏳ В холде: {stats.get('hold_total', 0):.2f} Stars\n"
        f"💎 Успешно выплачено: {stats.get('withdrawn_total', 0):.2f} Stars\n\n"
    )
    if top_users:
        text += "🏆 <b>Топ-5 активных участников:</b>\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, u in enumerate(top_users[:5]):
            name = f"@{u['username']}" if u.get("username") else u.get("first_name", "user")
            text += (
                f"{medals[i]} {name} — {u['tasks_done']} зад. "
                f"({u['balance']:.2f} ⭐️)\n"
            )
    return text


# ============= ПРОМОКОДЫ =============

def promo_activated_text(amount: float, balance: float) -> str:
    return (
        "🎉 <b>Промокод активирован!</b>\n\n"
        f"⭐ Вам начислено {amount:.2f} Stars на баланс.\n"
        f"💰 Ваш баланс: {balance:.2f} ⭐️"
    )


PROMO_ALREADY_USED = (
    "⚠️ Вы уже активировали этот промокод.\n\n"
    "Один промокод можно активировать только один раз."
)
PROMO_LIMIT_REACHED = (
    "😔 К сожалению, этот промокод больше не активен.\n\n"
    "Лимит активаций исчерпан. Следите за новыми промокодами!"
)
PROMO_NOT_FOUND = "❌ Промокод не найден или недействителен."


# ============= РЕКЛАМА =============

def ad_stat_text(ad: dict) -> str:
    return (
        f"📊 <b>Статистика рекламы: {ad['name']}</b>\n\n"
        f"🔗 Код: <code>/stat_{ad['code']}</code>\n"
        f"👤 Владелец: <code>{ad['owner_id']}</code>\n"
        f"💵 Цена за переход: {ad['price']:.2f}\n\n"
        f"👥 Переходов: {ad['clicks']}\n"
        f"✅ Заданий выполнено: {ad['tasks_done']}"
    )


AD_ACCESS_DENIED = "⛔ У вас нет доступа к этой рекламе."
