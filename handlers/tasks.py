import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import database as db
import texts
import keyboards
from services import get_all_tasks, check_task_in_services, Task

router = Router()
log = logging.getLogger("handlers.tasks")

user_active_tasks: dict[int, list[Task]] = {}

async def _get_next_task(user_id: int) -> Task | None:
    user = await db.get_user(user_id)
    if not user: return None
    skipped = user.get("skipped_tasks", [])
    if user_id not in user_active_tasks or not user_active_tasks[user_id]:
        user_active_tasks[user_id] = await get_all_tasks(user_id)
    tasks = user_active_tasks[user_id]
    for t in tasks:
        if t.key() not in skipped: return t
    return None

async def show_tasks_menu(message_or_cb, user_id: int, bot: Bot):
    task = await _get_next_task(user_id)
    if not task:
        user = await db.get_user(user_id)
        me = await bot.get_me()
        text_ = texts.tasks_finished_text(user["balance"], me.username, user_id)
        kb = keyboards.tasks_finished_kb(me.username, user_id)
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.message.edit_text(text_, reply_markup=kb)
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(text_, reply_markup=kb)
        return

    user = await db.get_user(user_id)
    skipped = user.get("skipped_tasks", [])
    total_available = sum(1 for t in user_active_tasks[user_id] if t.key() not in skipped)
    reward = await db.get_setting("task_reward", 0.4)
    service_name = keyboards.SERVICES.get(task.service, task.service)
    
    text_ = texts.task_text(index=1, total=total_available, source=service_name, sponsor=task.title, reward=reward)
    kb = keyboards.task_kb(task.url)

    if isinstance(message_or_cb, CallbackQuery):
        try:
            await message_or_cb.message.edit_text(text_, reply_markup=kb)
        except Exception:
            await message_or_cb.message.answer(text_, reply_markup=kb)
        await message_or_cb.answer()
    else:
        await message_or_cb.answer(text_, reply_markup=kb)

@router.message(F.text == "⭐️ Заработать Звезды")
async def cmd_earn_stars(message: Message, bot: Bot, state: FSMContext):
    await state.clear() # Сбрасываем состояния админки, если они застряли
    await db.update_user(message.from_user.id, skipped_tasks=[])
    user_active_tasks.pop(message.from_user.id, None)
    await show_tasks_menu(message, message.from_user.id, bot)

@router.callback_query(F.data == "go_earn")
async def cb_go_earn(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    await db.update_user(callback.from_user.id, skipped_tasks=[])
    user_active_tasks.pop(callback.from_user.id, None)
    await show_tasks_menu(callback, callback.from_user.id, bot)

@router.callback_query(F.data == "task_skip")
async def cb_skip_task(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    task = await _get_next_task(user_id)
    if task:
        user = await db.get_user(user_id)
        skipped = user.get("skipped_tasks", [])
        skipped.append(task.key())
        await db.update_user(user_id, skipped_tasks=skipped)
    await show_tasks_menu(callback, user_id, bot)

@router.callback_query(F.data == "task_check")
async def cb_check_task(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    task = await _get_next_task(user_id)
    if not task:
        return await callback.answer("Задание не найдено", show_alert=True)

    await callback.answer("⏳ Проверяем подписку...")
    is_done = await check_task_in_services(user_id, task)
    
    if not is_done:
        return await callback.answer(texts.TASK_NOT_SUBSCRIBED_TOAST, show_alert=True)

    reward = await db.get_setting("task_reward", 0.4)
    await db.add_hold(user_id, reward, kind="task", task_id=task.key())
    
    user = await db.get_user(user_id)
    ref_id = user.get("referrer_id")
    if ref_id:
        ref_percent = await db.get_setting("ref_percent", 10)
        ref_amount = round(reward * (ref_percent / 100.0), 4)
        if ref_amount > 0:
            await db.add_hold(ref_id, ref_amount, kind="ref", from_user=user_id, task_id=task.key())
            await db.add_ref_earned(ref_id, ref_amount)
            try:
                await bot.send_message(ref_id, texts.ref_earned_text(user.get("username"), user_id, ref_amount))
            except Exception: pass

    await db.increment_tasks_done(user_id)
    if user_id in user_active_tasks:
        user_active_tasks[user_id] = [t for t in user_active_tasks[user_id] if t.key() != task.key()]

    await callback.answer(texts.task_done_toast(reward), show_alert=True)
    await show_tasks_menu(callback, user_id, bot)
