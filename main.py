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
import sponsors
from ads import show_ad
from config import ADMIN_IDS, BOT_TOKEN, WITHDRAW_OPTIONS, fmt
from database import (
    activate_withdrawal, add_user, cancel_wait, check_ref_reward,
    count_refs, create_withdrawal, finish_task, get_setting, get_user,
    get_withdrawal, init_db, wait_progress,
)
from keyboards import (
    BTN_EARN, BTN_TASKS, BTN_WITHDRAW, main_kb, ref_kb, req_notify_kb,
    task_kb, wd_cancel_kb, withdraw_kb,
)
from sponsors import (
    check_task, current, full_id, get_next_task, skip_task, user_info,
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


async def alert_admins(text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


def disp(u):
    """@username или имя (для уведомлений)."""
    return escape(f"@{u.username}" if u.username else u.full_name)


# ---------- баны ----------

class Gate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = event.from_user
        if u is None or u.id in ADMIN_IDS:
            return await handler(event, data)
        row = await get_user(u.id)
        if row and row["banned"]:
            return
        is_start = (isinstance(event, Message)
                    and (event.text or "").startswith("/start"))
        if not row and not is_start:
            if isinstance(event, CallbackQuery):
                await event.answer("Нажми /start", show_alert=True)
            else:
                await event.answer("Нажми /start")
            return
        return await handler(event, data)


# ---------- сообщения ----------

async def send_ref(chat_id, uid):
    reward = await get_setting("ref_reward")
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    invited = await count_refs(uid)
    text = (
        f"<b>Получай +{fmt(reward)} ⭐ за каждого приглашённого "
        f"друга!</b>\n\n"
        f"📎 <i>Твоя реферальная ссылка:</i>\n{link}\n\n"
        f"🎉 <b>Приглашай по этой ссылке</b> своих друзей, отправляй её "
        f"во все чаты и <b>зарабатывай Звёзды</b>!\n\n"
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


async def announce_request(wid):
    """Заявка создана: уведомить пользователя, админов и канал."""
    w = await get_withdrawal(wid)
    if not w:
        return
    await notify(
        w["user_id"],
        f"✅ Заявка #{wid} на {fmt(w['amount'])} ⭐ создана.\n"
        "Срок вывода: 5 минут — 24 часа.")
    text = await admin_stats.new_request_text(wid)
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id, text, reply_markup=req_notify_kb(wid))
        except Exception:
            pass
    user = await get_user(w["user_id"])
    err = await admin_stats.post_channel(
        bot, "created", wid, w["amount"], user)
    if err:
        logging.warning("channel post error: %s", err)


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
        paid = await check_ref_reward(uid)
        prog = await wait_progress(uid)
        extra = ""
        ready = None
        if prog:
            if prog["done"] >= prog["need"]:
                if await activate_withdrawal(prog["w"]["id"]):
                    ready = prog["w"]["id"]
            else:
                extra = (f"\nДо вывода: {prog['done']}/{prog['need']} "
                         "заданий")
        await call.answer(f"✅ +{fmt(reward)} ⭐{extra}", show_alert=True)
        if paid:
            ref_id, ref_reward, need = paid
            await notify(
                ref_id,
                f"⭐ Твой реферал {disp(call.from_user)} выполнил "
                f"{fmt(need)} заданий: +{ref_reward:.2f} ⭐")
        if ready:
            await announce_request(ready)
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
    prog = await wait_progress(uid)
    if prog:
        left = max(prog["need"] - prog["done"], 0)
        await call.answer(
            f"У тебя уже есть вывод на {fmt(prog['w']['amount'])} ⭐. "
            f"Выполни ещё {left} заданий.", show_alert=True)
        return
    need = int(float(await get_setting("withdraw_tasks") or 0))
    res = await create_withdrawal(uid, amount, need)
    if not res:
        await call.answer("Недостаточно звёзд", show_alert=True)
        return
    wid, status = res
    await call.answer()
    if status == "new":
        await announce_request(wid)
        return
    await send(
        call.message.chat.id,
        f"⏳ Чтобы вывести {amount} ⭐, выполни {need} заданий. "
        "Как только выполнишь, заявка создастся автоматически.",
        reply_markup=wd_cancel_kb())
    await send_task(call.message.chat.id, user_info(call.from_user))


@dp.callback_query(F.data == "wd_cancel")
async def wd_cancel(call: CallbackQuery):
    uid = call.from_user.id
    prog = await wait_progress(uid)
    if not prog or not await cancel_wait(prog["w"]["id"], uid):
        await call.answer("Нечего отменять", show_alert=True)
        return
    await call.answer("Вывод отменён, звёзды вернулись на баланс",
                      show_alert=True)
    try:
        await call.message.delete()
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
    sponsors.set_alert(alert_admins)
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
