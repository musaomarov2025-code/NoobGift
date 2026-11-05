import asyncio
import aiohttp
import json
import time
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from main import ADMIN_ID, bot
from database import (
    get_user, add_user, update_balance, deduct_balance, create_withdrawal, get_setting,
    get_next_show, get_welcome_promo, get_services, is_task_completed,
    add_task_completion, check_ref_reward
)
from keyboards import user_main_kb, earn_inline_kb, withdraw_inline_kb, task_inline_kb

user_router = Router()

active_tasks = {}
api_error_cooldown = {}

async def notify_admin_error(service_name, error_msg):
    current_time = time.time()
    if current_time - api_error_cooldown.get(service_name, 0) > 3600:
        api_error_cooldown[service_name] = current_time
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ <b>Ошибка API [{service_name}]</b>\n{error_msg}")
        except: pass

async def send_promo(message: Message, promo):
    if not promo: return
    kb = None
    if promo['buttons']:
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
    elif promo['media_type'] == 'sticker':
        await message.answer_sticker(promo['media_id'])
        if promo['text'] or kb:
            await message.answer(promo['text'], reply_markup=kb, disable_web_page_preview=True)
    else:
        await message.answer(promo['text'], reply_markup=kb, disable_web_page_preview=True)

async def show_promo_cycle(message: Message):
    promo = await get_next_show()
    if promo:
        await send_promo(message, promo)

async def get_earn_text(user_id, username):
    user = await get_user(user_id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_reward = await get_setting('ref_reward')
    ref_tasks = await get_setting('ref_tasks_needed')
    
    # Премиум эмодзи для Заработать (🌟 6026106482297147601)
    text = (f"Получай +{ref_reward} ⭐ за каждого приглашенного друга!\n\n"
            f"🔗 Твоя реферальная ссылка:\n{ref_link}\n\n"
            f"🎉 Приглашай по этой ссылке своих друзей, отправляй её во все чаты и зарабатывай Звёзды!\n\n"
            f"Приглашено тобой: {user['ref_count']} 👤\n\n"
            f"❤Как это работает:\n"
            f"╠ Отправь свою ссылку другу\n"
            f"╠ Друг заходит и выполняет {ref_tasks} заданий\n"
            f"╚ Ты получаешь {ref_reward}⭐ сразу же!")
    return text, ref_link

@user_router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Пользователь"
    args = message.text.split()
    ref_by = 0
    if len(args) > 1 and args[1].isdigit():
        ref_by = int(args[1])
        if ref_by == user_id:
            ref_by = 0

    user = await get_user(user_id)
    if not user:
        await add_user(user_id, username, ref_by)
    
    welcome = await get_welcome_promo()
    if welcome:
        await send_promo(message, welcome)
    
    await asyncio.sleep(3)
    
    # Блок Заработать
    text_earn, ref_link = await get_earn_text(user_id, username)
    await message.answer(text_earn, reply_markup=earn_inline_kb(ref_link))
    
    # Блок Задания + Клавиатура
    task_reward = await get_setting('task_reward')
    text_tasks = (f"💡 Получай Звёзды за простые задания! 👇\n\n"
                  f"🟢 Подпишись и нажми «Подтвердить»\n\n"
                  f"Вознаграждение: +{task_reward}⭐")
    await message.answer(text_tasks, reply_markup=user_main_kb())

@user_router.message(F.text == "⭐ Заработать")
async def menu_earn(message: Message):
    await show_promo_cycle(message)
    text_earn, ref_link = await get_earn_text(message.from_user.id, message.from_user.username)
    await message.answer(text_earn, reply_markup=earn_inline_kb(ref_link))

@user_router.message(F.text == "🎁 Вывести")
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
    success = await deduct_balance(callback.from_user.id, amount)
    
    if not success:
        await callback.answer(f"Не хватает звёзд.", show_alert=True)
        return
        
    wd_id = await create_withdrawal(callback.from_user.id, amount)
    await callback.message.edit_text(f"✅ Заявка #{wd_id} на {amount} ⭐ создана.\nСрок вывода: 5 минут — 24 часа.")
    await callback.answer()
    
    username = f"@{callback.from_user.username}" if callback.from_user.username else "Пользователь"
    try:
        await bot.send_message(ADMIN_ID, f"💸 <b>Новая заявка #{wd_id}!</b>\nЮзер: {username} (ID: {callback.from_user.id})\nСумма: {amount} ⭐")
    except: pass

async def fetch_task_from_api(service_name, api_key, user_id):
    if not api_key: return None
    async with aiohttp.ClientSession() as session:
        try:
            if service_name == "BotoHub":
                async with session.get(f"https://botohub.me/api/get-tasks?user_id={user_id}&is_task=true", headers={"Auth": api_key}) as resp:
                    text = await resp.text()
                    print(f"[BotoHub] Status: {resp.status} | Response: {text}")
                    if resp.status == 401:
                        await notify_admin_error(service_name, "Неверный API-ключ.")
                        return None
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            if data.get("task"):
                                return {"task_id": str(data["task"]["id"]), "link": data["task"]["link"]}
                        except: pass
            
            elif service_name == "Traffy":
                async with session.post("https://api.traffy.ai/tasks", headers={"x-publisher-api-key": api_key}, json={"user_id": user_id}) as resp:
                    text = await resp.text()
                    print(f"[Traffy] Status: {resp.status} | Response: {text}")
                    if resp.status == 401:
                        await notify_admin_error(service_name, "Неверный API-ключ.")
                        return None
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            if data.get("tasks"):
                                t = data["tasks"][0]
                                return {"task_id": str(t["id"]), "link": t["link"]}
                        except: pass
                            
            elif service_name == "SubGram":
                async with session.post("https://api.subgram.org/get-sponsors", headers={"Auth": api_key}, json={"user_id": user_id, "action": "newtask", "get_links": 1}) as resp:
                    text = await resp.text()
                    print(f"[SubGram] Status: {resp.status} | Response: {text}")
                    if resp.status in [401, 403]:
                        await notify_admin_error(service_name, "Неверный API-ключ.")
                        return None
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            if data.get("sponsors"):
                                s = data["sponsors"][0]
                                return {"task_id": str(s["resource_id"]), "link": s["link"]}
                        except: pass
                            
            elif service_name == "PiarFlow":
                async with session.post("https://piarflow.com/v1/sponsors", headers={"Authorization": f"Bearer {api_key}"}, json={"user_id": user_id}) as resp:
                    text = await resp.text()
                    print(f"[PiarFlow] Status: {resp.status} | Response: {text}")
                    if resp.status == 401:
                        await notify_admin_error(service_name, "Неверный API-ключ.")
                        return None
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            if data.get("sponsors"):
                                s = data["sponsors"][0]
                                return {"task_id": str(s["id"]), "link": s["link"]}
                        except: pass
                            
            elif service_name == "Flyer":
                async with session.post("https://api.flyerhubs.com/get_tasks", json={"key": api_key, "user_id": user_id}) as resp:
                    text = await resp.text()
                    print(f"[Flyer] Status: {resp.status} | Response: {text}")
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            if data.get("tasks"):
                                t = data["tasks"][0]
                                return {"task_id": t["signature"], "link": t["links"][0]}
                        except: pass
                            
            elif service_name == "Tgrass":
                async with session.post("https://tgrass.space/tasks", headers={"Auth": api_key}, json={"tg_user_id": user_id, "is_premium": False, "lang": "ru"}) as resp:
                    text = await resp.text()
                    print(f"[Tgrass] Status: {resp.status} | Response: {text}")
                    if resp.status == 401:
                        await notify_admin_error(service_name, "Неверный API-ключ.")
                        return None
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                            offers = data.get("offers", [])
                            if offers:
                                o = offers[0]
                                if o.get("id") and o.get("link"):
                                    return {"task_id": str(o["id"]), "link": o["link"]}
                        except: pass
                            
        except Exception as e:
            print(f"[{service_name}] Exception: {e}")
    return None

async def check_task_in_api(service_name, api_key, user_id, task_id):
    async with aiohttp.ClientSession() as session:
        try:
            if service_name == "BotoHub":
                async with session.get(f"https://botohub.me/api/get-tasks?user_id={user_id}&is_task=true", headers={"Auth": api_key}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            if not data.get("task") or str(data["task"]["id"]) != task_id:
                                return True
                        except: pass
                    return False

            elif service_name == "Traffy":
                async with session.post("https://api.traffy.ai/tasks/check", headers={"x-publisher-api-key": api_key}, json={"user_id": user_id, "assignment_ids": [task_id]}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            return data.get("status") == "completed"
                        except: pass
                    return False
                    
            elif service_name == "SubGram":
                async with session.post("https://api.subgram.org/get-sponsors", headers={"Auth": api_key}, json={"user_id": user_id, "action": "subscribe"}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            return data.get("status") == "ok"
                        except: pass
                    return False
                    
            elif service_name == "PiarFlow":
                async with session.post("https://piarflow.com/v1/sponsors/check", headers={"Authorization": f"Bearer {api_key}"}, json={"user_id": user_id, "offer_id": task_id}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            return data.get("status") == "subscribed"
                        except: pass
                    return False
                    
            elif service_name == "Flyer":
                async with session.post("https://api.flyerhubs.com/check_task", json={"key": api_key, "user_id": user_id, "signature": task_id}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            return data.get("status") == "complete"
                        except: pass
                    return False
                    
            elif service_name == "Tgrass":
                async with session.post("https://tgrass.space/check", headers={"Auth": api_key}, json={"tg_user_id": user_id, "offer_id": task_id}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        try:
                            data = json.loads(text)
                            return data.get("status") == "ok"
                        except: pass
                    return False

        except Exception as e:
            print(f"Check Error {service_name}: {e}")
            return False
    return False

async def get_next_task(user_id):
    services = await get_services()
    reward = float(await get_setting('task_reward') or 0.65)
    
    for srv in services:
        if not srv['is_active'] or not srv['api_key']: continue
        
        task = await fetch_task_from_api(srv['name'], srv['api_key'], user_id)
        if task:
            if not await is_task_completed(user_id, srv['name'], task['task_id']):
                active_tasks[user_id] = {
                    "service": srv['name'],
                    "api_key": srv['api_key'],
                    "task_id": task['task_id'],
                    "link": task['link'],
                    "reward": reward
                }
                return active_tasks[user_id]
    return None

@user_router.message(F.text == "💎 Задания")
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
    active_tasks.pop(user_id, None) 
    await callback.answer("Задание пропущено", show_alert=True)
    await callback.message.delete()
    
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
        
    await callback.answer("⏳ Проверяем подписку...", show_alert=False)
    success = await check_task_in_api(task['service'], task['api_key'], user_id, task['task_id'])
    
    if success:
        await add_task_completion(user_id, task['service'], task['task_id'])
        await update_balance(user_id, task['reward'])
        await callback.message.delete()
        
        await callback.message.answer(
            f"✅ Задание выполнено!\n\n"
            f"Получено: +{task['reward']:.2f} ⭐\n\n"
            f"❗️ Не отписывайся от канала в течение как минимум 3 дней. В противном случае, ты получишь штраф."
        )
        
        ref_by, ref_rew, ref_username = await check_ref_reward(user_id)
        if ref_by:
            r_name = f"@{ref_username}" if ref_username != "Пользователь" else "Пользователь"
            try:
                await bot.send_message(ref_by, f"⭐ Твой реферал {r_name} выполнил нужное кол-во заданий: +{ref_rew:.2f} ⭐")
            except: pass
            
        active_tasks.pop(user_id, None)
    else:
        await callback.answer("❌ Задание не выполнено. Вы не подписались или отписались от канала.", show_alert=True)
