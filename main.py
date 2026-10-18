import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from urllib.parse import quote

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import (
    BOT_TOKEN, ADMIN_ID, DB, WITHDRAW_AMOUNTS,
    BOTOHUB_TOKEN, BOTOHUB_URL,
    PIARFLOW_TOKEN, PIARFLOW_URL,
    TGRASS_TOKEN, TGRASS_URL,
    TRAFSLY_TOKEN, TRAFSLY_URL,
    DEFAULTS
)
import database as db
import keyboards as kb

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ================== FSM ==================
class WithdrawState(StatesGroup):
    waiting_amount = State()
    
class AdminStates(StatesGroup):
    waiting_sponsor_name = State()
    waiting_sponsor_link = State()
    waiting_sponsor_id = State()
    waiting_give_stars = State()
    waiting_broadcast = State()
    waiting_avatar = State()
    waiting_promo_sum = State()
    waiting_promo_act = State()
    waiting_setting_value = State()
    waiting_user_info = State()

# ================== ХЕЛПЕР ==================
def _smart_text(message):
    return message.html_text if message.entities else message.text

def format_amount(amount):
    return f"{amount:.2f}".rstrip('0').rstrip('.') if amount % 1 else f"{amount:.0f}"

async def send_with_avatar(message: Message, text: str, reply_markup=None):
    # В твоем старом коде ава хранилась в priv, но мы можем использовать menu_avatar
    avatar = db.get_setting("menu_avatar")
    if avatar:
        await message.answer_photo(photo=avatar, caption=text, reply_markup=reply_markup)
    else:
        await message.answer(text=text, reply_markup=reply_markup)

# ================== BOTOHUB (ОП) ==================
def bh_enabled():
    return db.get_setting("botohub_enabled") == "1"

async def bh_get_tasks(chat_id, count):
    if not BOTOHUB_TOKEN: return {"tasks": [], "completed": True, "skip": True}
    payload = {"chat_id": chat_id, "max_op": count}
    headers = {"Auth": BOTOHUB_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(BOTOHUB_URL, json=payload, headers=headers, timeout=15) as r:
                return await r.json()
    except Exception as e:
        print("Botohub ОП error:", e)
        return {"tasks": [], "completed": True, "skip": True}

async def collect_op_items(user_id):
    if not bh_enabled(): return []
    try:
        count = int(db.get_setting("botohub_entry_count") or 2)
    except: count = 2
    data = await bh_get_tasks(user_id, count)
    tasks = data.get("tasks", [])
    return [(t.get('url'), "Подписаться", t.get('url'), False) for t in tasks if not t.get("completed") and t.get("url")]

async def check_op_and_proceed(call_or_message, user_id):
    items = await collect_op_items(user_id)
    if not items:
        db.set_op_passed(user_id)
        ref_id = db.confirm_referral(user_id)
        if ref_id:
            ref_bonus = int(db.get_setting("ref_bonus"))
            db.add_balance(ref_id, ref_bonus)
            try:
                await bot.send_message(ref_id, f'<tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji> Твой реферал прошел ОП: <b>+{ref_bonus} ⭐</b>')
            except: pass
        return True
    else:
        text = db.get_setting("sub_text").format(channel_name="Спонсоры")
        kb = kb.op_screen_kb(items)
        if isinstance(call_or_message, CallbackQuery):
            await call_or_message.message.edit_text(text, reply_markup=kb)
        else:
            await call_or_message.answer(text, reply_markup=kb)
        return False

# ================== API СЕРВИСОВ ЗАДАНИЙ ==================
async def fetch_task_piarflow(user_id):
    headers = {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}
    payload = {"user_id": user_id, "chat_id": user_id, "max_sponsors": 1}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(f"{PIARFLOW_URL}/sponsors", json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    sponsors = data.get("sponsors", [])
                    if sponsors:
                        return {"service": "piarflow", "task_id": sponsors[0]["link"], "link": sponsors[0]["link"]}
        except: pass
    return None

async def fetch_task_tgrass(user_id):
    headers = {"Auth": TGRASS_TOKEN}
    payload = {"tg_user_id": user_id, "is_premium": False, "lang": "ru"}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(TGRASS_URL, json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    offers = data.get("offers", [])
                    if offers and data.get("status") == "not_ok":
                        return {"service": "tgrass", "task_id": str(offers[0]["offer_id"]), "link": offers[0]["link"]}
        except: pass
    return None

async def fetch_task_trafsly(user_id):
    headers = {"Auth": TRAFSLY_TOKEN}
    payload = {"user_id": user_id}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(TRAFSLY_URL, json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    sponsors = data.get("sponsors", [])
                    if sponsors and data.get("status") == "warning":
                        return {"service": "trafsly", "task_id": str(sponsors[0]["ads_id"]), "link": sponsors[0]["link"]}
        except: pass
    return None

async def fetch_new_task(user_id):
    t = await fetch_task_piarflow(user_id)
    if not t: t = await fetch_task_tgrass(user_id)
    if not t: t = await fetch_task_trafsly(user_id)
    return t

async def check_task_status(service, user_id, task_id):
    if service == "piarflow":
        headers = {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}
        payload = {"user_id": user_id, "links": [task_id]}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{PIARFLOW_URL}/sponsors/check", json=payload, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    elif service == "tgrass":
        headers = {"Auth": TGRASS_TOKEN}
        payload = {"tg_user_id": user_id, "offer_id": int(task_id)}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://tgrass.space/check", json=payload, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("status") == "subscribed"
    elif service == "trafsly":
        headers = {"Auth": TRAFSLY_TOKEN}
        payload = {"user_id": user_id, "ads_id": task_id}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json=payload, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("subscribed") is True
    return False

# ================== СТАРТ ==================
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id == user_id: ref_id = None

    is_new = db.add_user(user_id, message.from_user.username, ref_id)
    if not is_new:
        db.update_username(user_id, message.from_user.username)
    else:
        if ref_id: db.create_pending_referral(user_id, ref_id)

    u = db.get_user(user_id)
    if not u['welcome_bonus_paid']:
        bonus = int(db.get_setting("welcome_bonus"))
        db.add_balance(user_id, bonus)
        db.mark_welcome_bonus_paid(user_id)
        await message.answer(f"🎁 Вам начислен приветственный бонус: <b>{bonus} ⭐</b>")

    passed = await check_op_and_proceed(message, user_id)
    if not passed:
        return

    await send_main_menu(message)

async def send_main_menu(message: Message):
    text = db.get_setting("menu_text").format(ref_bonus=db.get_setting("ref_bonus"))
    await send_with_avatar(message, text, kb.main_menu_kb())

@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery):
    passed = await check_op_and_proceed(call, call.from_user.id)
    if passed:
        try: await call.message.delete()
        except: pass
        await send_main_menu(call.message)
    await call.answer()

# ================== МЕНЮ ==================
@dp.callback_query(F.data == "menu_back")
async def back_to_menu(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    await send_main_menu(call.message)
    await call.answer()

@dp.callback_query(F.data == "menu_refs")
async def show_refs(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    uid = call.from_user.id
    u = db.get_user(uid)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={uid}"
    
    refs = db.get_user_referrals(uid)
    ref_list_text = ""
    for r in refs:
        name = f"@{r['username']}" if r['username'] else f"id {r['user_id']}"
        status = "проходит ОП" if r['status'] == 'pending' else "✅ Засчитан"
        ref_list_text += f"├ {name} — {status}\n"
    if not ref_list_text: ref_list_text = "├ Пока никого нет\n"
    
    text = db.get_setting("ref_text").format(
        ref_bonus=db.get_setting("ref_bonus"),
        ref_link=ref_link,
        total_refs=db.get_pending_refs_count(uid) + db.get_confirmed_refs_count(uid),
        confirmed_refs=db.get_confirmed_refs_count(uid),
        ref_list=ref_list_text,
        balance=format_amount(u['balance'])
    )
    await send_with_avatar(call.message, text, kb.back_kb())

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    name = f"@{u['username']}" if u['username'] else u['first_name']
    text = db.get_setting("profile_text").format(
        username=name,
        total_refs=db.get_pending_refs_count(u['user_id']) + db.get_confirmed_refs_count(u['user_id']),
        total_earned=format_amount(u['total_earned']),
        balance=format_amount(u['balance']),
        user_id=u['user_id'],
        tasks_completed=db.get_task_stats()['count'] # Заглушка, лучше считать по user_id
    )
    await send_with_avatar(call.message, text, kb.back_kb())

# ================== ЗАДАНИЯ ==================
@dp.callback_query(F.data == "menu_earn")
async def show_tasks(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, call.from_user.id)
    await call.answer()

async def send_next_task(message: Message, user_id: int):
    task = db.get_pending_task(user_id)
    if not task:
        new_task = await fetch_new_task(user_id)
        if not new_task:
            await message.answer("😔 На данный момент нет доступных заданий.", reply_markup=kb.back_kb())
            return
        db.save_task(user_id, new_task["service"], new_task["task_id"], new_task["link"])
        task = db.get_pending_task(user_id)

    text = db.get_setting("task_text")
    await message.answer(text, reply_markup=kb.task_kb(task["link"]))

@dp.callback_query(F.data == "check_task")
async def check_task(call: CallbackQuery):
    user_id = call.from_user.id
    task = db.get_pending_task(user_id)
    if not task:
        await call.answer("Задание не найдено.", show_alert=True)
        return
    await call.message.edit_text("⏳ Проверяем...")
    is_done = await check_task_status(task['service'], user_id, task['task_id'])
    if is_done:
        reward = float(db.get_setting("task_reward"))
        db.add_balance(user_id, reward)
        db.mark_task_completed(user_id, task['service'], task['task_id'], reward)
        db.mark_task_status(task['id'], 'done')
        await call.message.edit_text(f"✅ Выполнено! Начислено: {format_amount(reward)} ⭐")
        await asyncio.sleep(1.5)
        try: await call.message.delete()
        except: pass
        await send_next_task(call.message, user_id)
    else:
        await call.message.edit_text("❌ Не выполнено.", reply_markup=kb.task_kb(task["link"]))
    await call.answer()

@dp.callback_query(F.data == "skip_task")
async def skip_task(call: CallbackQuery):
    user_id = call.from_user.id
    task = db.get_pending_task(user_id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено", show_alert=True)
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, user_id)

# ================== СТАТИСТИКА (ТОПЫ) ==================
@dp.callback_query(F.data == "menu_stats")
async def show_stats(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    text = db.get_setting("stats_text").format(
        total_users=db.get_stats()['total'],
        total_withdrawn=format_amount(db.get_stats()['total_stars'])
    )
    await send_with_avatar(call.message, text, kb.stats_kb())

@dp.callback_query(F.data.startswith("top_"))
async def show_top(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    top_type = call.data.split("_")[1]
    if top_type == "balance":
        top = db.get_top_balance()
        text = "💰 <b>Топ по балансу</b>\n\n"
        for i, u in enumerate(top, 1):
            name = f"@{u['username']}" if u['username'] else f"id {u['user_id']}"
            text += f"{i}. {name} — {format_amount(u['balance'])} ⭐\n"
    else:
        top = db.get_top_refs()
        text = "👥 <b>Топ по рефералам</b>\n\n"
        for i, u in enumerate(top, 1):
            name = f"@{u['username']}" if u['username'] else f"id {u['user_id']}"
            text += f"{i}. {name} — {u['refs']}\n"
            
    await call.message.answer(text, reply_markup=kb.back_kb("menu_stats"))

# ================== ВЫВОД ==================
@dp.callback_query(F.data == "menu_withdraw")
async def show_withdraw(call: CallbackQuery, state: FSMContext):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    amounts = ", ".join(map(str, WITHDRAW_AMOUNTS))
    text = db.get_setting("withdraw_text").format(balance=format_amount(u['balance']), amounts=amounts)
    await send_with_avatar(call.message, text, kb.withdraw_kb())
    await state.set_state(WithdrawState.waiting_amount)

@dp.callback_query(WithdrawState.waiting_amount, F.data.startswith("wd_"))
async def process_wd_btn(call: CallbackQuery, state: FSMContext):
    amount = float(call.data.split("_")[1])
    await process_withdraw(call.message, call.from_user.id, amount)
    await state.clear()
    await call.answer()

async def process_withdraw(message: Message, uid: int, amount: float):
    u = db.get_user(uid)
    if u['balance'] < amount:
        await message.answer(f"Не хватает звёзд. Баланс: {format_amount(u['balance'])} ⭐")
        return
    req_friends = int(db.get_setting("withdraw_friends_required"))
    if db.get_confirmed_refs_count(uid) < req_friends:
        await message.answer(f"⚠️ <b>Недостаточно друзей!</b>\nНужно: {req_friends}")
        return
    
    wid = db.create_withdrawal(uid, amount)
    await message.answer(f"✅ Заявка #{wid} на {format_amount(amount)} ⭐ создана.", reply_markup=kb.back_kb())

# ================== АДМИНКА ==================
@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery):
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

# ================== ЗАПУСК ==================
async def main():
    db.init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
