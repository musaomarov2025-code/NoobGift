import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery

import admin
from config import BOT_TOKEN, ADMIN_IDS
from database import (
    init_db, add_user, get_user, get_setting, count_refs,
    finish_task, check_ref_reward, add_balance, create_withdrawal,
)
from keyboards import (
    main_kb, ref_kb, task_kb, withdraw_kb,
    BTN_EARN, BTN_TASKS, BTN_WITHDRAW,
)
from sponsors import (
    get_next_task, check_task, skip_task, current, full_id, user_info,
)

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
dp.include_router(admin.router)


async def send_ref(message: Message, user_id: int):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={user_id}"
    reward = await get_setting("ref_reward")
    need = await get_setting("ref_tasks_needed")
    invited = await count_refs(user_id)
    text = (
        f"Получай +{reward} ⭐ за каждого приглашённого друга!\n\n"
        f"📎 Твоя реферальная ссылка:\n{link}\n\n"
        f"🎉 Приглашай друзей и зарабатывай Звёзды!\n"
        f"Награда начисляется, когда друг выполнит {need} зад.\n\n"
        f"Приглашено тобой: {invited}"
    )
    await message.answer(text, reply_markup=ref_kb(link))


async def send_task(message: Message, user):
    task = await get_next_task(user_info(user))
    if not task:
        await message.answer("Заданий пока нет, загляни чуть позже ⏳")
        return
    reward = await get_setting("task_reward")
    text = (
        "💡 Получай Звёзды за простые задания! 👇\n\n"
        f"🟢 {task['text']}\n\n"
        f"Вознаграждение: +{reward} ⭐"
    )
    await message.answer(text, reply_markup=task_kb(task.get("url")))


@dp.message(CommandStart())
async def start(message: Message, command: CommandObject):
    uid = message.from_user.id
    ref = None
    if command.args and command.args.isdigit():
        ref = int(command.args)
    await add_user(uid, message.from_user.username, ref)
    await message.answer("👋 Добро пожаловать!", reply_markup=main_kb)
    await send_ref(message, uid)
    await send_task(message, message.from_user)


@dp.message(F.text == BTN_EARN)
async def earn(message: Message):
    await send_ref(message, message.from_user.id)


@dp.message(F.text == BTN_TASKS)
async def tasks(message: Message):
    await send_task(message, message.from_user)


@dp.callback_query(F.data == "task_skip")
async def task_skip(call: CallbackQuery):
    uid = call.from_user.id
    skip_task(uid)
    await call.message.delete()
    await send_task(call.message, call.from_user)
    await call.answer()


@dp.callback_query(F.data == "task_check")
async def task_check(call: CallbackQuery):
    uid = call.from_user.id
    task = current.get(uid)
    if not task:
        await call.answer("Задание устарело", show_alert=True)
        await call.message.delete()
        await send_task(call.message, call.from_user)
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
        await call.answer(f"✅ +{reward} ⭐", show_alert=True)
        paid = await check_ref_reward(uid)
        if paid:
            ref_id, ref_reward = paid
            try:
                await bot.send_message(
                    ref_id,
                    f"🎉 Твой друг выполнил задания! +{ref_reward} ⭐")
            except Exception:
                pass
    current.pop(uid, None)
    await call.message.delete()
    await send_task(call.message, call.from_user)


@dp.message(F.text == BTN_WITHDRAW)
async def withdraw(message: Message):
    u = await get_user(message.from_user.id)
    min_w = float(await get_setting("min_withdraw"))
    bal = u["balance"] if u else 0
    text = f"💰 Твой баланс: {bal:.2f} ⭐\nМинимум для вывода: {min_w:g} ⭐"
    if bal >= min_w:
        await message.answer(text, reply_markup=withdraw_kb(bal))
    else:
        await message.answer(
            text + "\n\nПродолжай выполнять задания и приглашай друзей!")


@dp.callback_query(F.data == "withdraw")
async def withdraw_confirm(call: CallbackQuery):
    uid = call.from_user.id
    u = await get_user(uid)
    min_w = float(await get_setting("min_withdraw"))
    if not u or u["balance"] < min_w:
        await call.answer("Недостаточно звёзд", show_alert=True)
        return
    res = await create_withdrawal(uid)
    if not res:
        await call.answer("Ошибка, попробуй позже", show_alert=True)
        return
    wid, amount = res
    await call.message.edit_text(
        f"✅ Заявка №{wid} на {amount:.2f} ⭐ создана. "
        "Ожидай выплату.")
    name = call.from_user.username or call.from_user.full_name
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💸 Заявка на вывод №{wid}\n"
                f"Пользователь: {name} (ID {uid})\n"
                f"Сумма: {amount:.2f} ⭐")
        except Exception:
            pass
    await call.answer()


async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
