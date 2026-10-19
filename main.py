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
from aiogram.utils.keyboard import InlineKeyboardBuilder

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

# ================== ХЕЛПЕР ==================
def _smart_text(message):
    return message.html_text if message.entities else message.text

def format_amount(amount):
    return f"{amount:.2f}".rstrip('0').rstrip('.') if amount % 1 else f"{amount:.0f}"

async def send_with_avatar(message: Message, text: str, reply_markup=None):
    avatar = db.get_setting("menu_avatar")
    if avatar:
        await message.answer_photo(photo=avatar, caption=text, reply_markup=reply_markup)
    else:
        await message.answer(text=text, reply_markup=reply_markup)

# ================== FSM ==================
class WithdrawState(StatesGroup):
    waiting_amount = State()

class AdminStates(StatesGroup):
    waiting_promo_sum = State()
    waiting_promo_act = State()
    waiting_setting_value = State()
    waiting_give_stars = State()
    waiting_user_info = State()
    waiting_broadcast = State()
    waiting_avatar = State()
    waiting_ad_code = State()
    waiting_ad_owner = State()

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
        return {"tasks": [], "completed": True, "skip": True}

async def collect_op_items(user_id):
    if not bh_enabled(): return []
    try: count = int(db.get_setting("botohub_entry_count") or 2)
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
                await bot.send_message(ref_id, f'<tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji> Твой реферал прошел Обязательную подписку: <b>+{ref_bonus} ⭐</b>')
            except: pass
        return True
    else:
        text = db.get_setting("botohub_text")
        kb_op = kb.op_screen_kb(items)
        if isinstance(call_or_message, CallbackQuery):
            await call_or_message.message.edit_text(text, reply_markup=kb_op)
        else:
            await call_or_message.answer(text, reply_markup=kb_op)
        return False

# ================== API ЗАДАНИЙ (3 СЕРВИСА) ==================
async def fetch_task_piarflow(user_id):
    headers = {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}
    payload = {"user_id": user_id, "chat_id": user_id, "max_sponsors": 1}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(f"{PIARFLOW_URL}/sponsors", json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    sponsors = data.get("sponsors", [])
                    if sponsors: return {"service": "piarflow", "task_id": sponsors[0]["link"], "link": sponsors[0]["link"]}
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
    # ================== СТАРТ, ПРИВАТКА И ОП ==================
@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
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

    # 1. Приватка (если включена)
    if db.get_setting("priv_enabled") == "1":
        priv_text = db.get_setting("priv_text")
        # Если нужно, здесь можно добавить кнопки приватки из настроек
        await message.answer(priv_text, parse_mode="HTML")
        await asyncio.sleep(3) # Пауза 3 секунды

    # 2. Обязательная подписка (Botohub)
    passed = await check_op_and_proceed(message, user_id)
    if not passed: return

    # 3. Меню
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

# ================== МЕНЮ: РАЗДЕЛЫ ==================
@dp.callback_query(F.data == "menu_back")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
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
        status = "проходит подписку" if r['status'] == 'pending' else "✅ Засчитан"
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
    name = f"@{u['username']}" if u['username'] else "Юзер"
    text = db.get_setting("profile_text").format(
        username=name,
        total_refs=db.get_pending_refs_count(u['user_id']) + db.get_confirmed_refs_count(u['user_id']),
        total_earned=format_amount(u['total_earned']),
        balance=format_amount(u['balance']),
        user_id=u['user_id'],
        tasks_completed=u['tasks_completed']
    )
    await send_with_avatar(call.message, text, kb.back_kb())

@dp.callback_query(F.data == "menu_instruction")
async def show_instruction(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    await send_with_avatar(call.message, db.get_setting("instruction_text"), kb.back_kb())

@dp.callback_query(F.data == "menu_stats")
async def show_stats(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    s = db.get_stats()
    text = db.get_setting("stats_text").format(
        total_users=s['total'],
        total_withdrawn=format_amount(s['total_stars'])
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
            
    await send_with_avatar(call.message, text, kb.back_kb("menu_stats"))

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
    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> Заявка <b>#{wid}</b> на <b>{format_amount(amount)}</b> ⭐ создана.\n\n'
        f'Срок вывода: 5 минут — 24 часа.'
    )
    await message.answer(text, reply_markup=kb.back_kb())

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
        old_task = db.get_task_by_link(user_id, new_task["link"])
        if old_task:
            new_task = await fetch_new_task(user_id)
            if not new_task or db.get_task_by_link(user_id, new_task["link"]):
                await message.answer("😔 Больше нет новых заданий.", reply_markup=kb.back_kb())
                return
        
        db.save_task(user_id, new_task["service"], new_task["task_id"], new_task["link"])
        task = db.get_pending_task(user_id)

    text = db.get_setting("task_text").format(reward=db.get_setting("task_reward"))
    await message.answer(text, reply_markup=kb.task_kb(task["link"]))

@dp.callback_query(F.data == "check_task")
async def check_task(call: CallbackQuery):
    user_id = call.from_user.id
    task = db.get_pending_task(user_id)
    if not task: return await call.answer("Задание не найдено.", show_alert=True)
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
    task = db.get_pending_task(call.from_user.id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено", show_alert=True)
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, call.from_user.id)
    # ================== АДМИНКА ==================
@dp.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "admin_back", StateFilter("*"))
async def admin_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if call.from_user.id != ADMIN_ID: return
    try:
        await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())
    except:
        await call.message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())
    await call.answer()

# --- Статистика ---
@dp.callback_query(F.data == "stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    s = db.get_stats()
    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Юзеров: {s['total']}\n"
        f"💰 Баланс: {s['total_balance']}\n"
        f"📋 Заявок: {s['pending']}\n"
        f"✅ Выполнено: {s['done']}",
        reply_markup=kb.back_admin_kb()
    )

# --- Настройки ---
@dp.callback_query(F.data == "settings")
async def admin_settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"👥 Реф-бонус: <b>{db.get_setting('ref_bonus')}</b>\n"
        f"💰 За задание: <b>{db.get_setting('task_reward')}</b>\n"
        f"🤝 Друзей для вывода: <b>{db.get_setting('withdraw_friends_required')}</b>",
        reply_markup=kb.settings_kb()
    )

@dp.callback_query(F.data.startswith("set:"))
async def set_value_ask(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    key = call.data.split(":")[1]
    await state.update_data(set_key=key)
    await call.message.answer("Введи новое значение:")
    await state.set_state(AdminStates.waiting_setting_value)

@dp.message(AdminStates.waiting_setting_value)
async def set_value_save(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    db.set_setting(data['set_key'], message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=kb.back_admin_kb())

# --- Начислить звезды ---
@dp.callback_query(F.data == "give_start")
async def give_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.answer("Введи ID юзера и сумму через пробел:")
    await state.set_state(AdminStates.waiting_give_stars)

@dp.message(AdminStates.waiting_give_stars)
async def process_give_stars(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        uid, amount = map(float, message.text.split())
        db.add_balance(int(uid), amount)
        await message.answer(f"✅ Начислено {format_amount(amount)} ⭐ юзеру {int(uid)}", reply_markup=kb.back_admin_kb())
    except: 
        await message.answer("Ошибка. Введи ID и сумму.")
    await state.clear()

# --- Заявки на вывод ---
async def _render_wd_page(call_or_message, idx=0):
    wds = db.get_pending_withdrawals()
    if not wds:
        if isinstance(call_or_message, CallbackQuery):
            await call_or_message.message.edit_text("📭 Заявок нет", reply_markup=kb.back_admin_kb())
        else:
            await call_or_message.answer("📭 Заявок нет", reply_markup=kb.back_admin_kb())
        return
    if idx < 0: idx = 0
    if idx >= len(wds): idx = len(wds) - 1
    wd = wds[idx]
    text = f"💸 <b>Заявка #{wd['id']}</b>\n👤 ID: <code>{wd['user_id']}</code>\n💰 Сумма: <b>{format_amount(wd['amount'])}</b> ⭐"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wd['id']}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wd['id']}")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"wd_page:{idx-1}"),
        InlineKeyboardButton(text=f"{idx+1}/{len(wds)}", callback_data="ignore"),
        InlineKeyboardButton(text="➡️", callback_data=f"wd_page:{idx+1}")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    if isinstance(call_or_message, CallbackQuery):
        try: await call_or_message.message.edit_text(text, reply_markup=builder.as_markup())
        except: pass
    else:
        await call_or_message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data == "wd_list")
async def wd_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await _render_wd_page(call, 0)

@dp.callback_query(F.data.startswith("wd_page:"))
async def wd_page(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    idx = int(call.data.split(":")[1])
    await _render_wd_page(call, idx)
    await call.answer()

@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    wid = int(call.data.split(":")[1])
    db.set_withdrawal_status(wid, "completed")
    wd = db.get_withdrawal(wid)
    try:
        await bot.send_message(wd['user_id'], f"✅ Заявка #{wid} на {format_amount(wd['amount'])} ⭐ выплачена!")
    except: pass
    await call.answer("Одобрено")
    await _render_wd_page(call, 0)

@dp.callback_query(F.data.startswith("wd_no:"))
async def wd_no(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    wid = int(call.data.split(":")[1])
    db.set_withdrawal_status(wid, "rejected")
    wd = db.get_withdrawal(wid)
    db.add_balance(wd['user_id'], wd['amount'])
    try:
        await bot.send_message(wd['user_id'], f"❌ Заявка #{wid} отклонена, звезды возвращены.")
    except: pass
    await call.answer("Отклонено")
    await _render_wd_page(call, 0)

# --- Смена Авы ---
@dp.callback_query(F.data == "admin_change_avatar")
async def admin_change_avatar(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.answer("Отправь фото для меню:")
    await state.set_state(AdminStates.waiting_avatar)

@dp.message(AdminStates.waiting_avatar, F.photo)
async def process_avatar(message: Message, state: FSMContext):
    db.set_setting("menu_avatar", message.photo[-1].file_id)
    await message.answer("✅ Ава обновлена!", reply_markup=kb.back_admin_kb())
    await state.clear()

# --- Рассылка ---
@dp.callback_query(F.data == "broadcast_menu")
async def broadcast_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("📢 Отправь текст (или фото с текстом) для рассылки:", reply_markup=kb.back_admin_kb())

@dp.message(F.text | F.photo, StateFilter(None))
async def process_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID: return
    users = db.get_all_user_ids()
    await message.answer(f"Начинаю рассылку для {len(users)}...")
    success = 0
    for u in users:
        try:
            if message.photo:
                await bot.send_photo(u, message.photo[-1].file_id, caption=message.html_text)
            else:
                await bot.send_message(u, message.html_text)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {success}", reply_markup=kb.back_admin_kb())

# --- Бэкап ---
@dp.callback_query(F.data == "backup_help")
async def backup_help(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    try:
        doc = FSInputFile(DB)
        await call.message.answer_document(doc, caption="💾 Бэкап БД")
    except Exception as e:
        await call.message.answer(f"Ошибка: {e}")
    await call.answer()

# ================== ФОН: АВТО-БЭКАП ==================
async def daily_backup():
    while True:
        try:
            now = datetime.now()
            targets = [now.replace(hour=8, minute=0, second=0, microsecond=0), now.replace(hour=20, minute=0, second=0, microsecond=0)]
            next_run = next((t for t in targets if t > now), targets[0] + timedelta(days=1))
            await asyncio.sleep((next_run - now).total_seconds())
            try:
                doc = FSInputFile(DB)
                await bot.send_document(ADMIN_ID, doc, caption=f"📦 Авто-бэкап\n{now.strftime('%d.%m.%Y %H:%M')}")
            except: pass
        except Exception: 
            await asyncio.sleep(3600)

# ================== ЗАПУСК ==================
async def main():
    db.init_db()
    asyncio.create_task(daily_backup())
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
