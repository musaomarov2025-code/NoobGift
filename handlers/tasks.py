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

# Кэш активных заданий, чтобы не дергать API 5 сервисов на каждое нажатие кнопки
user_active_tasks: dict[int, list[Task]] = {}


async def _get_next_task(user: dict) -> Task | None:
    """Возвращает первое доступное задание, которое юзер ещё не пропустил."""
    skipped = user.get("skipped_tasks", [])
    uid = user["user_id"]
    
    # Если кэша нет или он пуст — грузим заново
    if uid not in user_active_tasks or not user_active_tasks[uid]:
        user_active_tasks[uid] = await get_all_tasks(user)

    tasks = user_active_tasks[uid]

    # Ищем первое задание, которое не пропущено
    for t in tasks:
        if t.key() not in skipped:
            return t

    return None


async def show_tasks_menu(message_or_cb, user: dict, bot: Bot):
    """Показывает текущее задание или сообщение об окончании заданий."""
    task = await _get_next_task(user)
    
    if not task:
        # Задания закончились
        me = await bot.get_me()
        text_ = texts.tasks_finished_text(user["balance"], me.username, user["user_id"])
        kb = keyboards.tasks_finished_kb(me.username, user["user_id"])
        
        if isinstance(message_or_cb, CallbackQuery):
            try:
                await message_or_cb.message.edit_text(text_, reply_markup=kb)
            except Exception:
                await message_or_cb.message.answer(text_, reply_markup=kb)
            await message_or_cb.answer()
        else:
            await message_or_cb.answer(text_, reply_markup=kb)
        return

    skipped = user.get("skipped_tasks", [])
    total_available = sum(1 for t in user_active_tasks[user["user_id"]] if t.key() not in skipped)
    
    reward = await db.get_setting("task_reward", 0.4)
    service_name = keyboards.SERVICES.get(task.service, task.service)
    
    text_ = texts.task_text(
        index=1, 
        total=total_available, 
        source=service_name, 
        sponsor=task.title, 
        reward=reward
    )
    
    kb = keyboards.task_kb(task.url)

    if isinstance(message_or_cb, CallbackQuery):
        try:
            await message_or_cb.message.edit_text(text_, reply_markup=kb)
        except Exception:
            # Если сообщение не изменилось (например, нажали дважды) или это медиа
            await message_or_cb.message.answer(text_, reply_markup=kb)
        await message_or_cb.answer()
    else:
        await message_or_cb.answer(text_, reply_markup=kb)


@router.message(F.text == "⭐️ Заработать Звезды")
async def cmd_earn_stars(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user:
        # Сбрасываем пропущенные задания
        await db.update_user(message.from_user.id, skipped_tasks=[])
        user_active_tasks.pop(message.from_user.id, None)
        
        # ВАЖНО: перезагружаем юзера из базы, чтобы сбросить старые пропуски
        user = await db.get_user(message.from_user.id) 
        await show_tasks_menu(message, user, bot)


@router.callback_query(F.data == "go_earn")
async def cb_go_earn(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    if user:
        await db.update_user(callback.from_user.id, skipped_tasks=[])
        user_active_tasks.pop(callback.from_user.id, None)
        
        # Перезагружаем юзера
        user = await db.get_user(callback.from_user.id) 
        await show_tasks_menu(callback, user, bot)


@router.callback_query(F.data == "task_skip")
async def cb_skip_task(callback: CallbackQuery, bot: Bot):
    user = await db.get_user(callback.from_user.id)
    if not user: return
    
    task = await _get_next_task(user)
    if task:
        skipped = user.get("skipped_tasks", [])
        skipped.append(task.key())
        await db.update_user(user["user_id"], skipped_tasks=skipped)
        
        # Перезагружаем юзера, чтобы новое пропущенное задание учлось
        user = await db.get_user(callback.from_user.id)
        
    await show_tasks_menu(callback, user, bot)


@router.callback_query(F.data == "task_check")
async def cb_check_task(callback: CallbackQuery, bot: Bot):
    user = await db.get_user(callback.from_user.id)
    if not user: return
    
    task = await _get_next_task(user)
    if not task: 
        return await callback.answer("Задание не найдено", show_alert=True)

    await callback.answer("⏳")
    is_done = await check_task_in_services(user, task)
    
    if not is_done:
        # Убрали show_alert, просто тихо даем фидбек крестиком
        return await callback.answer("❌ Вы не подписались")

    # === ЗАДАНИЕ ВЫПОЛНЕНО ===
    reward = await db.get_setting("task_reward", 0.4)
    
    # 1. Начисляем юзеру в холд
    await db.add_hold(user["user_id"], reward, kind="task", task_id=task.key())
    
    # 2. Начисляем рефереру
    ref_id = user.get("referrer_id")
    if ref_id:
        ref_percent = await db.get_setting("ref_percent", 10)
        ref_amount = round(reward * (ref_percent / 100.0), 4)
        if ref_amount > 0:
            await db.add_hold(ref_id, ref_amount, kind="ref", from_user=user["user_id"], task_id=task.key())
            await db.add_ref_earned(ref_id, ref_amount)
            
            try:
                await bot.send_message(ref_id, texts.ref_earned_text(user.get("username"), user["user_id"], ref_amount))
            except Exception: 
                pass

    # 3. Обновляем счетчики
    await db.increment_tasks_done(user["user_id"])
    
    # 4. Убираем задание из кэша, чтобы не выдалось снова
    if user["user_id"] in user_active_tasks:
        user_active_tasks[user["user_id"]] = [t for t in user_active_tasks[user["user_id"]] if t.key() != task.key()]

    # Убрали show_alert, просто показываем галочку
    await callback.answer("✅ Выполнено!")
    
    # Показываем следующее задание
    await show_tasks_menu(callback, user, bot)
