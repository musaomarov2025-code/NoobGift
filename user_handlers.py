import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from main import ADMIN_ID, bot
from database import (
    get_user, add_user, update_balance, create_withdrawal, get_setting,
    get_next_show, get_welcome_promo
)
from keyboards import user_main_kb, earn_inline_kb, withdraw_inline_kb, task_inline_kb

user_router = Router()

# Временное хранилище текущего задания для юзера (в оперативке, чтобы не грузить БД лишний раз)
user_current_task = {}

async def send_promo(message: Message, promo):
    """Вспомогательная функция для отправки показов/приветки"""
    if not promo: return
    kb = None
    if promo['buttons']:
        import json
        buttons = json.loads(promo['buttons'])
        builder = InlineKeyboardBuilder()
        for row in buttons:
            for btn in row:
                builder.button(text=btn['text'], url=btn['url'])
            builder.adjust(*[len(r) for r in buttons])
        kb = builder.as_markup()
        
    if promo['media_type'] == 'photo':
        await message.answer_photo(promo['media_id'], caption=promo['text'], reply_markup=kb)
    elif promo['media_type'] == 'video':
        await message.answer_video(promo['media_id'], caption=promo['text'], reply_markup=kb)
    else:
        await message.answer(promo['text'], reply_markup=kb, disable_web_page_preview=True)

async def show_promo_cycle(message: Message):
    """Показывает очередь показов"""
    promo = await get_next_show()
    if promo:
        await send_promo(message, promo)

@user_router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Пользователь"
    args = message.text.split()
    ref_by = 0
    if len(args) > 1 and args[1].isdigit():
        ref_by = int(args[1])
        if ref_by == user_id:
            ref_by = 0 # Защита от самого себя

    user = await get_user(user_id)
    if not user:
        await add_user(user_id, username, ref_by)
        if ref_by:
            ref_user = await get_user(ref_by)
            if ref_user:
                ref_name = f"@{username}" if message.from_user.username else "Пользователь"
                try:
                    await bot.send_message(ref_by, f"⚡️ {ref_name} присоединился по твоей ссылке!\n\nТы получишь {await get_setting('ref_reward')} ⭐, как только он выполнит {await get_setting('ref_tasks_needed')} заданий")
                except:
                    pass
    
    # Приветка
    welcome = await get_welcome_promo()
    if welcome:
        await send_promo(message, welcome)
    
    await asyncio.sleep(3) # Задержка 3 секунды
    
    await message.answer("💰 <b>Заработать</b>\nПолучай +5 ⭐️ за каждого приглашенного друга!\n\n📎 Твоя реферальная ссылка:\nhttps://t.me/{(await bot.get_me()).username}?start={user_id}")
    
    await message.answer("💡 <b>Задания</b>\nПолучай Звёзды за простые задания!")
    
    await message.answer("Главное меню:", reply_markup=user_main_kb())

@user_router.message(F.text == "Заработать")
async def menu_earn(message: Message):
    await show_promo_cycle(message)
    user_id = message.from_user.id
    user = await get_user(user_id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (f"💰 Получай +5 ⭐️ за каждого приглашенного друга!\n\n"
            f"📎 Твоя реферальная ссылка:\n{ref_link}\n\n"
            f"🎉 Приглашай по этой ссылке своих друзей, отправляй её во все чаты и зарабатывай ⭐️!\n\n"
            f"👥 Приглашено тобой: {user['ref_count']}\n"
            f"⭐️ Заработано с рефералов: {user['ref_earned']:.2f}")
            
    await message.answer(text, reply_markup=earn_inline_kb(ref_link))

@user_router.message(F.text == "Вывести")
async def menu_withdraw(message: Message):
    await show_promo_cycle(message)
    user = await get_user(message.from_user.id)
    balance = user['balance']
    
    if balance < 15.0:
        await message.answer(f"Не хватает звёзд. Баланс: {balance:.2f} ⭐")
        return
        
    await message.answer(f"Ваш баланс: {balance:.2f} ⭐️\n\nВыберите сколько хотите вывести.", reply_markup=withdraw_inline_kb())

@user_router.callback_query(F.data.startswith("wd_"))
async def process_withdraw(callback: CallbackQuery):
    amount = float(callback.data.split("_")[1])
    user = await get_user(callback.from_user.id)
    
    if user['balance'] < amount:
        await callback.answer(f"Не хватает звёзд. Баланс: {user['balance']:.2f} ⭐", show_alert=True)
        return
        
    # Списываем баланс сразу (резервируем)
    await update_balance(callback.from_user.id, -amount)
    wd_id = await create_withdrawal(callback.from_user.id, amount)
    
    await callback.message.edit_text(f"✅ Заявка #{wd_id} на {amount} ⭐ создана.\nСрок вывода: 5 минут — 24 часа.")
    await callback.answer()
    
    # Уведомление админу
    username = f"@{callback.from_user.username}" if callback.from_user.username else "Пользователь"
    try:
        await bot.send_message(ADMIN_ID, f"💸 <b>Новая заявка #{wd_id}!</b>\nЮзер: {username} (ID: {callback.from_user.id})\nСумма: {amount} ⭐")
    except:
        pass
      import aiohttp
import json
from database import (
    get_services, get_setting, is_task_completed, 
    add_task_completion, check_ref_reward
)

# Хранилище активных заданий юзера {user_id: {"service": name, "task_id": id, "link": url, "reward": float}}
active_tasks = {}

async def fetch_task_from_api(service_name, api_key, user_id):
    """Запрашивает задание у конкретного сервиса"""
    if not api_key: return None
    async with aiohttp.ClientSession() as session:
        try:
            if service_name == "BotoHub":
                async with session.get(f"https://botohub.me/api/get-tasks?user_id={user_id}&is_task=true", headers={"Auth": api_key}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("task"):
                            return {"task_id": str(data["task"]["id"]), "link": data["task"]["link"]}
            
            elif service_name == "Traffy":
                async with session.post("https://api.traffy.ai/tasks", headers={"x-publisher-api-key": api_key}, json={"user_id": user_id}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("tasks"):
                            t = data["tasks"][0]
                            return {"task_id": str(t["id"]), "link": t["link"]}
                            
            elif service_name == "SubGram":
                async with session.post("https://api.subgram.org/get-sponsors", headers={"Auth": api_key}, json={"user_id": user_id, "action": "newtask", "get_links": 1}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("sponsors"):
                            s = data["sponsors"][0]
                            return {"task_id": str(s["resource_id"]), "link": s["link"]}
                            
            elif service_name == "PiarFlow":
                async with session.post("https://piarflow.com/v1/sponsors", headers={"Authorization": f"Bearer {api_key}"}, json={"user_id": user_id}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("sponsors"):
                            s = data["sponsors"][0]
                            return {"task_id": str(s["id"]), "link": s["link"]}
                            
            elif service_name == "Flyer":
                async with session.post("https://api.flyerhubs.com/get_tasks", json={"key": api_key, "user_id": user_id}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("tasks"):
                            t = data["tasks"][0]
                            return {"task_id": t["signature"], "link": t["links"][0]}
                            
            elif service_name == "Tgrass":
                async with session.post("https://tgrass.space/tasks", headers={"Auth": api_key}, json={"tg_user_id": user_id, "is_premium": False, "lang": "ru"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("offers"):
                            o = data["offers"][0]
                            return {"task_id": str(o["id"]), "link": o["link"]}
                            
        except Exception as e:
            print(f"API Error {service_name}: {e}")
    return None

async def get_next_task(user_id):
    """Ищет следующее доступное задание по приоритету"""
    services = await get_services()
    reward = float(await get_setting('task_reward') or 0.65)
    
    for srv in services:
        if not srv['is_active']: continue
        
        task = await fetch_task_from_api(srv['name'], srv['api_key'], user_id)
        if task:
            # Проверяем, не выполнял ли он его ранее
            if not await is_task_completed(user_id, srv['name'], task['task_id']):
                active_tasks[user_id] = {
                    "service": srv['name'],
                    "task_id": task['task_id'],
                    "link": task['link'],
                    "reward": reward
                }
                return active_tasks[user_id]
    return None

@user_router.message(F.text == "Задания")
async def menu_tasks(message: Message):
    await show_promo_cycle(message)
    user_id = message.from_user.id
    
    task = await get_next_task(user_id)
    if not task:
        await message.answer("😴 Заданий пока нет — загляни позже.")
        return
        
    text = (f"💡 Получай Звёзды за простые задания! 👇\n\n"
            f"🟢 Подпишись и нажми «Подтвердить»\n\n"
            f"Вознаграждение: +{task['reward']:.2f}⭐")
            
    await message.answer(text, reply_markup=task_inline_kb(task['link']))

@user_router.callback_query(F.data == "task_skip")
async def task_skip(callback: CallbackQuery):
    user_id = callback.from_user.id
    active_tasks.pop(user_id, None) # Удаляем текущее
    await callback.answer("Задание пропущено", show_alert=True)
    await callback.message.delete()
    
    # Выдаем следующее
    task = await get_next_task(user_id)
    if not task:
        await callback.message.answer("😴 Заданий пока нет — загляни позже.")
        return
        
    text = (f"💡 Получай Звёзды за простые задания! 👇\n\n"
            f"🟢 Подпишись и нажми «Подтвердить»\n\n"
            f"Вознаграждение: +{task['reward']:.2f}⭐")
    await callback.message.answer(text, reply_markup=task_inline_kb(task['link']))

@user_router.callback_query(F.data == "task_confirm")
async def task_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id
    task = active_tasks.get(user_id)
    
    if not task:
        await callback.answer("Задание устарело или не найдено.", show_alert=True)
        return
        
    # Здесь должна быть проверка выполнения через API сервиса (упрощено для примера)
    # В реальности: отправляем запрос на check endpoint сервиса с task_id.
    # Для примера считаем, что если юзер нажал, то он подписался.
    success = True 
    
    if success:
        # Начисляем
        await add_task_completion(user_id, task['service'], task['task_id'])
        await update_balance(user_id, task['reward'])
        await callback.message.delete()
        
        await callback.message.answer(
            f"✅ Задание выполнено!\n\n"
            f"Получено: +{task['reward']:.2f} ⭐\n\n"
            f"❗️ Не отписывайся от канала в течение как минимум 3 дней. В противном случае, ты получишь штраф."
        )
        
        # Проверяем рефералку (не пора ли выдать бонус пригласившему)
        ref_by, ref_rew, ref_username = await check_ref_reward(user_id)
        if ref_by:
            r_name = f"@{ref_username}" if ref_username != "Пользователь" else "Пользователь"
            try:
                await bot.send_message(ref_by, f"⭐ Твой реферал {r_name} выполнил 5 заданий: +{ref_rew:.2f} ⭐")
            except: pass
            
        active_tasks.pop(user_id, None)
        await callback.answer("Успешно!")
    else:
        await callback.answer("❌ Задание не выполнено. Подписка не найдена или истекла.", show_alert=True)
