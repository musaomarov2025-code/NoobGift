import asyncio
import logging
from html import escape

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

import admin
import admin_ads
import admin_db
import admin_stats
import daily
import webapp
from ads import show_ad
from config import ADMIN_IDS, BOT_TOKEN, WEBAPP_URL, WITHDRAW_OPTIONS, fmt
from database import (
    add_user, check_ref_reward, count_refs, create_withdrawal,
    finish_task, get_setting, get_user, init_db,
)
from keyboards import (
    BTN_EARN, BTN_TASKS, BTN_WITHDRAW, check_kb, main_kb, ref_kb,
    req_notify_kb, task_kb, withdraw_kb,
)
from sponsors import (
    check_task, current, full_id, get_next_task, skip_task, user_info,
    user_info_row,
)

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise SystemExit("Нет BOT_TOKEN: добавь переменную в настройках хостинга")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
BOT_USERNAME = ""
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def send(chat_id, text, **kw):
    return await bot.send_message(
        chat_id, text, parse_mode="HTML",
        link_preview_options=NO_PREVIEW, **kw)


async def notify(uid, text):
    try:
        await send(uid, text)
    except Exception:
        pass


def disp(u):
    """@username или имя (для уведомлений)."""
    return escape(f"@{u.username}" if u.username else u.full_name)


# ---------- проверка доступа и баны ----------

class Gate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = event.from_user
        if u is None or u.id in ADMIN_IDS:
            return await handler(event, data)
        is_start = (isinstance(event, Message)
                    and (event.text or "").startswith("/start"))
        row = await get_user(u.id)
        if row and row["banned"]:
            return
        if is_start:
            return await handler(event, data)
        if not row:
            await self._say(event, "Нажми /start")
            return
        if WEBAPP_URL and not row["verified"]:
            await self._say(event, "Сначала пройди проверку: нажми /start",
                            check=True)
            return
        return await handler(event, data)

    @staticmethod
    async def _say(event, text, check=False):
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif check:
            await send_check(event.chat.id)
        else:
            await event.answer(text)


async def send_check(chat_id):
    await send(
        chat_id, "<b>Для доступа к боту пройди быструю проверку</b> 👇",
        reply_markup=check_kb())


# ---------- сообщения ----------

async def send_ref(chat_id, uid):
    reward = await get_setting("ref_reward")
    need = await get_setting("ref_tasks_needed")
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    invited = await count_refs(uid)
    text = (
        f"<b>Получай +{fmt(reward)} ⭐ за каждого приглашённого "
        f"друга!</b>\n\n"
        f"📎 <i>Твоя реферальная ссылка:</i>\n{link}\n\n"
        f"🎉 <b>Приглашай по этой ссылке</b> своих друзей, отправляй её "
        f"во все чаты и <b>зарабатывай Звёзды</b>!\n"
        f"Награда придёт, когда друг выполнит {fmt(need)} зад.\n\n"
        f"<b>Приглашено тобой:</b> {invited}"
    )
    await send(chat_id, text, reply_markup=ref_kb(link))


async def send_task(chat_id, info, with_ad=False):
    task = await get_next_task(info)
    if not task:
        await send(chat_id, "Заданий пока нет, загляни чуть позже ⏳")
    else:
        reward = await get_setting("task_reward")
        text = (
            "💡 Получай <b>Звёзды</b> за <b>простые задания</b>! 👇\n\n"
            f"🟢 {escape(task['text'])}\n\n"
            f"Вознаграждение: +{fmt(reward)} ⭐"
        )
        await send(chat_id, text, reply_markup=task_kb(task.get("url")))
    if with_ad:
        await show_ad(bot, chat_id)


async def welcome(chat_id, info):
    await send(chat_id, "⭐️", reply_markup=main_kb)
    await send_ref(chat_id, info["id"])
    await send_task(chat_id, info)


async def on_verified(uid):
    """Вызывается после успешной проверки в мини-приложении."""
    row = await get_user(uid)
    if row:
        await welcome(uid, user_info_row(row))


# ---------- обработчики ----------

@dp.message(CommandStart())
async def start(message: Message, command: CommandObject):
    u = message.from_user
    ref = None
    if command.args and command.args.isdigit():
        ref = int(command.args)
    created, ref_id = await add_user(
        u.id, u.username, u.first_name, u.language_code or "ru",
        int(bool(u.is_premium)), ref)
    if created and ref_id:
        reward = await get_setting("ref_reward")
        need = await get_setting("ref_tasks_needed")
        await notify(
            ref_id,
            f"⚡️ {disp(u)} присоединился по твоей ссылке!\n\n"
            f"Ты получишь {fmt(reward)} ⭐, как только он выполнит "
            f"{fmt(need)} заданий")
    row = await get_user(u.id)
    if WEBAPP_URL and not row["verified"] and u.id not in ADMIN_IDS:
        await send_check(message.chat.id)
        return
    await welcome(message.chat.id, user_info(u))


@dp.message(F.text == BTN_EARN)
async def earn(message: Message):
    await send_ref(message.chat.id, message.from_user.id)
    await show_ad(bot, message.chat.id)


@dp.message(F.text == BTN_TASKS)
async def tasks(message: Message):
    await send_task(
        message.chat.id, user_info(message.from_user), with_ad=True)


@dp.callback_query(F.data == "task_skip")
async def task_skip(call: CallbackQuery):
    skip_task(call.from_user.id)
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await send_task(call.message.chat.id, user_info(call.from_user))


@dp.callback_query(F.data == "task_check")
async def task_check(call: CallbackQuery):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    task = current.get(uid)
    if not task:
        await call.answer("Задание устарело", show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        await send_task(chat_id, user_info(call.from_user))
        return
    if not await check_task(uid, task):
        await call.answer(
            "❌ Подписка не найдена. Подпишись и нажми ещё раз.",
            show_alert=True)
        return
    reward = float(await get_setting("task_reward"))
    if not await finish_task(uid, full_id(task), reward):
        await call.answer("Это задание уже засчитано", show_alert=True)
    else:
        await call.answer(f"✅ +{fmt(reward)} ⭐", show_alert=True)
        paid = await check_ref_reward(uid)
        if paid:
            ref_id, ref_reward, need = paid
            await notify(
                ref_id,
                f"⭐ Твой реферал {disp(call.from_user)} выполнил "
                f"{fmt(need)} заданий: +{ref_reward:.2f} ⭐")
    current.pop(uid, None)
    try:
        await call.message.delete()
    except Exception:
        pass
    await send_task(chat_id, user_info(call.from_user))


@dp.message(F.text == BTN_WITHDRAW)
async def withdraw(message: Message):
    row = await get_user(message.from_user.id)
    bal = row["balance"] if row else 0
    await send(
        message.chat.id,
        f"<b>Ваш баланс:</b> {bal:.2f} ⭐️\n\n"
        "Выберите сколько хотите вывести.",
        reply_markup=withdraw_kb())
    await show_ad(bot, message.chat.id)


@dp.callback_query(F.data.startswith("withdraw:"))
async def withdraw_confirm(call: CallbackQuery):
    uid = call.from_user.id
    amount = int(call.data.split(":")[1])
    if amount not in WITHDRAW_OPTIONS:
        await call.answer()
        return
    wid = await create_withdrawal(uid, amount)
    if not wid:
        await call.answer("Недостаточно звёзд", show_alert=True)
        return
    await call.answer()
    await send(
        call.message.chat.id,
        f"✅ Заявка #{wid} на {amount} ⭐ создана.\n"
        "Срок вывода: 5 минут — 24 часа.")
    name = call.from_user.username or call.from_user.full_name
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💸 Новая заявка #{wid}\n{amount} ⭐ · {name} (ID {uid})",
                reply_markup=req_notify_kb(wid))
        except Exception:
            pass


@dp.callback_query(F.data == "daily_ref")
async def daily_ref(call: CallbackQuery):
    await call.answer()
    await send_ref(call.message.chat.id, call.from_user.id)


@dp.callback_query(F.data == "daily_tasks")
async def daily_tasks(call: CallbackQuery):
    await call.answer()
    await send_task(
        call.message.chat.id, user_info(call.from_user), with_ad=True)


# ---------- запуск ----------

dp.message.outer_middleware(Gate())
dp.callback_query.outer_middleware(Gate())
for r in (admin.router, admin_ads.router, admin_stats.router,
          admin_db.router, daily.router):
    dp.include_router(r)


async def main():
    global BOT_USERNAME
    await init_db()
    BOT_USERNAME = (await bot.get_me()).username
    await bot.delete_webhook(drop_pending_updates=True)
    if WEBAPP_URL:
        await webapp.start_server(on_verified)
    background = [
        asyncio.create_task(daily.daily_loop(bot)),
        asyncio.create_task(admin_db.backup_loop(bot)),
    ]
    try:
        await dp.start_polling(bot)
    finally:
        for t in background:
            t.cancel()


if __name__ == "__main__":
    asyncio.run(main())
