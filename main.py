import asyncio
import logging
import random
import re
import json
import os
import shutil
from datetime import datetime
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter, BaseFilter
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Document
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import *
import database as db
import keyboards as kb

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class IsAdminFilter(BaseFilter):
    async def __call__(self, event) -> bool: return db.is_admin(event.from_user.id)

def fmt(amt): return f"{amt:.2f}".rstrip('0').rstrip('.') if amt % 1 else f"{amt:.0f}"
def safe_format(text: str, **kwargs):
    for k, v in kwargs.items(): text = text.replace("{" + k + "}", str(v))
    return text

async def send_av(message, text, markup=None):
    av = db.get_setting("menu_avatar")
    if av:
        try: 
            await message.answer_photo(photo=av, caption=text, reply_markup=markup)
            return
        except Exception: pass
    try:
        await message.answer(text=text, reply_markup=markup)
    except Exception as e:
        print(f"Ошибка текста: {e}")

class UserStates(StatesGroup):
    w_amount = State()

class AdminStates(StatesGroup):
    w_sp_name = State()
    w_sp_url = State()
    w_sp_chat = State()
    w_u_search = State()
    w_u_bal = State()
    w_set_val = State()

# ================= API =================
async def pf_get(uid):
    token = PIARFLOW_TOKEN
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(f"{PIARFLOW_URL}/sponsors", json={"user_id": uid, "chat_id": uid, "max_sponsors": 1}, headers={"Authorization": f"Bearer {token}"}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp and sp[0].get("status") == "unsubscribed": return {"srv": "piarflow", "tid": sp[0]["link"], "link": sp[0]["link"]}
        except Exception: pass
    return None
async def pf_check(uid, tid):
    token = PIARFLOW_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{PIARFLOW_URL}/sponsors/check", json={"user_id": uid, "links": [tid]}, headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    return False

async def tg_get(uid):
    token = TGRASS_TOKEN
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://tgrass.space/tasks", json={"tg_user_id": uid, "is_premium": False, "lang": "ru"}, headers={"Auth": token}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "not_ok" and d.get("offers"):
                        for offer in d["offers"]:
                            if not offer.get("subscribed"): return {"srv": "tgrass", "tid": str(offer["offer_id"]), "link": offer["link"]}
        except Exception: pass
    return None
async def tg_check(uid, tid):
    token = TGRASS_TOKEN
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://tgrass.space/check", json={"tg_user_id": uid, "offer_id": int(tid)}, headers={"Auth": token}, timeout=10) as r:
                if r.status != 200: return False
                d = await r.json()
                if d.get("status") == "subscribed": return True
        except Exception: pass
    return False

async def tr_get(uid):
    token = TRAFSLY_TOKEN
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://api.trafsly.com/api/v1/get-sponsors", json={"user_id": uid}, headers={"Auth": token}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp and d.get("status") == "warning": return {"srv": "trafsly", "tid": str(sp[0]["ads_id"]), "link": sp[0]["link"]}
        except Exception: pass
    return None
async def tr_check(uid, tid):
    token = TRAFSLY_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json={"user_id": uid, "ads_id": tid}, headers={"Auth": token}) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("subscribed") is True
    return False

async def get_new_task(uid):
    try:
        t = await tg_get(uid)
        if t: return t
        t = await pf_get(uid)
        if t: return t
        t = await tr_get(uid)
        if t: return t
    except Exception: pass
    return None

async def check_task_status(srv, uid, tid):
    if srv == "piarflow": return await pf_check(uid, tid)
    if srv == "tgrass": return await tg_check(uid, tid)
    if srv == "trafsly": return await tr_check(uid, tid)
    return False

# ================= СТАРТ =================
async def check_user_sponsors(uid):
    sponsors = db.get_sponsors()
    if not sponsors: return True
    for s in sponsors:
        try:
            member = await bot.get_chat_member(s['chat_id'], uid)
            if member.status in ['left', 'kicked']: return False
        except Exception: return False
    return True

@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else None

    ref_id = None
    if payload and payload.startswith("ref_"):
        try:
            ref_id = int(payload.replace("ref_", ""))
            if ref_id == uid: ref_id = None
        except Exception: pass

    u = db.get_user(uid)
    if u and u['is_banned']: return await message.answer("🚫 Вы забанены.")
    
    if not u:
        db.add_user(uid, message.from_user.username, ref_id)
        if ref_id:
            uname = message.from_user.first_name or "Пользователь"
            percent = db.get_setting("ref_percent")
            msg = f'<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> <b>Новый реферал!</b> Пользователь <b>{uname}</b> запустил бота по вашей ссылке.\nВы получаете <b>{percent}%</b> от его заработка!'
            try: await bot.send_message(ref_id, msg)
            except Exception: pass
    else:
        db.update_username(uid, message.from_user.username)

    if not await check_user_sponsors(uid):
        sponsors = db.get_sponsors()
        sp_list = "\n".join([f"├ {s['name']}" for s in sponsors])
        txt = safe_format(db.get_setting("sponsor_text"), sponsors=sp_list)
        return await message.answer(txt, reply_markup=kb.sponsor_kb(sponsors))

    await send_main_menu(message)

@dp.callback_query(F.data == "check_sponsors")
async def cb_check_sponsors(call: CallbackQuery):
    if await check_user_sponsors(call.from_user.id):
        try: await call.message.delete()
        except Exception: pass
        await send_main_menu(call.message)
        await call.answer()
    else:
        await call.answer("❌ Вы подписались не на все каналы!", show_alert=True)

async def send_main_menu(message: Message):
    t = safe_format(db.get_setting("menu_text"), ref_percent=db.get_setting("ref_percent"))
    await send_av(message, t, kb.main_menu_kb())

@dp.callback_query(F.data == "menu_back")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except Exception: pass
    await send_main_menu(call.message)
    await call.answer()

# ================= ЗАДАНИЯ =================
@dp.callback_query(F.data == "menu_earn")
async def show_tasks(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except Exception: pass
    await send_next_task(call.message, call.from_user.id)
    await call.answer()

async def send_next_task(message: Message, uid: int):
    try:
        task = db.get_pending_task(uid)
        if not task:
            new_t = await get_new_task(uid)
            if not new_t: return await message.answer("😔 Нет доступных заданий.", reply_markup=kb.back_kb())
            db.save_task(uid, new_t["srv"], new_t["tid"], new_t["link"])
            task = db.get_pending_task(uid)
        txt = safe_format(db.get_setting("task_text"), reward=db.get_setting("task_reward"), ref_percent=db.get_setting("ref_percent"))
        await message.answer(txt, reply_markup=kb.task_kb(task["link"]))
    except Exception as e:
        await message.answer("😔 Ошибка загрузки задания.", reply_markup=kb.back_kb())

@dp.callback_query(F.data == "check_task")
async def check_task_cb(call: CallbackQuery):
    uid = call.from_user.id
    task = db.get_pending_task(uid)
    if not task: return await call.answer("Задание не найдено.", show_alert=True)
    try: await call.message.edit_text("⏳ Проверяем...")
    except Exception: pass
    
    is_done = await check_task_status(task['service'], uid, task['task_id'])
    if not is_done and task['service'] == 'tgrass':
        await asyncio.sleep(2)
        is_done = await check_task_status(task['service'], uid, task['task_id'])

    if is_done:
        reward = float(db.get_setting("task_reward"))
        db.add_balance(uid, reward)
        db.add_task_completed(uid)
        db.mark_task_status(task['id'], 'done')
        
        u = db.get_user(uid)
        if u['referrer_id']:
            ref_percent = float(db.get_setting("ref_percent"))
            ref_bonus = round(reward * (ref_percent / 100), 2)
            if ref_bonus > 0:
                db.add_ref_earning(u['referrer_id'], ref_bonus)
                try: await bot.send_message(u['referrer_id'], f"⚡️ Твой реферал выполнил задание. Тебе начислено <b>{ref_bonus}</b> ⭐")
                except Exception: pass

        try: await call.message.edit_text(f"✅ Выполнено! Начислено: {fmt(reward)} ⭐")
        except Exception: pass
        await asyncio.sleep(1)
        try: await call.message.delete()
        except Exception: pass
        await send_next_task(call.message, uid)
    else:
        try: await call.message.edit_text("❌ Не выполнено.", reply_markup=kb.task_kb(task["link"]))
        except Exception: await call.answer("❌ Не выполнено.", show_alert=True)
    await call.answer()

@dp.callback_query(F.data == "skip_task")
async def skip_task_cb(call: CallbackQuery):
    task = db.get_pending_task(call.from_user.id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено")
    try: await call.message.delete()
    except Exception: pass
    await send_next_task(call.message, call.from_user.id)

# ================= ПРОФИЛЬ И РЕФЕРАЛЫ =================
@dp.callback_query(F.data == "menu_profile")
async def menu_profile(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    u = db.get_user(call.from_user.id)
    uname = "@" + u['username'] if u['username'] else "Юзер"
    t = safe_format(db.get_setting("profile_text"), 
        username=uname, total_refs=db.get_refs_count(u['user_id']), total_withdrawn=fmt(u['total_withdrawn']), 
        balance=fmt(u['balance']), user_id=u['user_id'], tasks_completed=u['tasks_completed'], ref_earnings=fmt(u['ref_earnings'])
    )
    await send_av(call.message, t, kb.back_kb())
    await call.answer()

@dp.callback_query(F.data == "menu_refs")
async def menu_refs(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    uid = call.from_user.id
    u = db.get_user(uid)
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    t = safe_format(db.get_setting("ref_text"), 
        ref_percent=db.get_setting("ref_percent"), ref_link=link, 
        total_refs=db.get_refs_count(uid), ref_earnings=fmt(u['ref_earnings'])
    )
    await send_av(call.message, t, kb.back_kb())
    await call.answer()

# ================= ВЫВОД =================
@dp.callback_query(F.data == "menu_withdraw")
async def menu_withdraw(call: CallbackQuery, state: FSMContext):
    try: await call.message.delete()
    except Exception: pass
    u = db.get_user(call.from_user.id)
    t = safe_format(db.get_setting("withdraw_text"), balance=fmt(u['balance']), amounts=", ".join(map(str, WITHDRAW_AMOUNTS)))
    await send_av(call.message, t, kb.withdraw_kb())
    await state.set_state(UserStates.w_amount)
    await call.answer()

async def do_withdraw(uid: int, message: Message, amount: float):
    u = db.get_user(uid)
    if not u: return await message.answer("❌ Ошибка.")
    if round(u['balance'], 2) < amount: 
        return await message.answer(f"❌ Не хватает. Баланс: {fmt(u['balance'])} ⭐")
    
    wid = db.create_withdrawal(uid, amount)
    txt = f'<tg-emoji emoji-id="5427009714745517609">✅</tg-emoji> Заявка <b>#{wid}</b> на <b>{fmt(amount)}</b> <tg-emoji emoji-id="5408869739982246969">⭐</tg-emoji> создана.\n\nСрок вывода: 5 минут — 24 часа.'
    await message.answer(txt, reply_markup=kb.back_kb())
    
    admin_msg = f"💸 <b>Заявка #{wid}</b>\n👤 @{u['username'] or 'нет'} (<code>{u['user_id']}</code>)\n💰 Сумма: {fmt(amount)}⭐\n👥 Рефов: {db.get_refs_count(uid)}\n🎯 Заданий: {u['tasks_completed']}\n💵 Остаток: {fmt(u['balance'] - amount)}⭐"
    try: await bot.send_message(ADMIN_ID, admin_msg)
    except Exception: pass

@dp.message(UserStates.w_amount)
async def process_wd_text(message: Message, state: FSMContext):
    try: amount = float(message.text.strip().replace(',', '.'))
    except ValueError: return await message.answer("❌ Введи число.")
    if amount not in WITHDRAW_AMOUNTS: return await message.answer(f"❌ Доступно: {', '.join(map(str, WITHDRAW_AMOUNTS))}")
    await state.clear()
    await do_withdraw(message.from_user.id, message, amount)

@dp.callback_query(F.data.regexp(r"^wd_\d+$"))
async def process_wd_btn(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except Exception: pass
    await do_withdraw(call.from_user.id, call.message, float(call.data.split("_")[1]))
    await call.answer()

# ================= СТАТИСТИКА =================
@dp.callback_query(F.data == "menu_stats")
async def menu_stats(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    t = "📊 <b>Статистика</b>\n\nВыбери раздел:"
    await call.message.answer(t, reply_markup=kb.stats_kb())
    await call.answer()

@dp.callback_query(F.data == "top_bal")
async def top_bal(call: CallbackQuery):
    users = db.get_top_balance()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по балансу</b>\n\n" + "".join([f"{i}. @{u['username'] or 'id'} — <b>{fmt(u['balance'])}</b> ⭐\n" for i, u in enumerate(users, 1)])
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer(txt, reply_markup=kb.back_kb("menu_stats"))
    await call.answer()

@dp.callback_query(F.data == "top_ref")
async def top_ref(call: CallbackQuery):
    users = db.get_top_refs()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по рефералам</b>\n\n" + "".join([f"{i}. @{u['username'] or 'id'} — <b>{u['cnt']}</b> чел.\n" for i, u in enumerate(users, 1)])
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer(txt, reply_markup=kb.back_kb("menu_stats"))
    await call.answer()

@dp.callback_query(F.data == "top_earn")
async def top_earn(call: CallbackQuery):
    users = db.get_top_earn()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по заработку</b>\n\n" + "".join([f"{i}. @{u['username'] or 'id'} — <b>{fmt(u['total_earned'])}</b> ⭐\n" for i, u in enumerate(users, 1)])
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer(txt, reply_markup=kb.back_kb("menu_stats"))
    await call.answer()
    # ================= АДМИНКА: БАЗА =================
@dp.message(Command("admin"), IsAdminFilter())
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "admin_back", StateFilter("*"), IsAdminFilter())
async def admin_back_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())
    except Exception: pass
    await call.answer()

@dp.callback_query(F.data == "admin_stats", IsAdminFilter())
async def admin_detailed_stats(c: CallbackQuery):
    s = db.get_stats()
    txt = "📊 <b>Статистика бота</b>\n\n"
    txt += "👥 Всего юзеров: <b>" + str(s['total']) + "</b>\n"
    txt += "🆕 За сегодня: <b>" + str(s['today']) + "</b>\n"
    txt += "💰 Общий баланс: <b>" + fmt(s['total_bal']) + "</b> ⭐\n"
    txt += "💸 В ожидании вывода: <b>" + fmt(s['pending_wd']) + "</b> ⭐"
    try: await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())
    except Exception: pass
    await c.answer()

# ================= АДМИНКА: СПОНСОРЫ =================
@dp.callback_query(F.data == "admin_sponsors", IsAdminFilter())
async def admin_sponsors_menu(c: CallbackQuery):
    sponsors = db.get_sponsors()
    txt = "🎯 <b>Твои спонсоры:</b>\n\n"
    if not sponsors:
        txt += "Список пуст. Добавь канал!"
    else:
        for s in sponsors:
            txt += f"🔹 {s['name']} | {s['url']}\n"
            
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Добавить", callback_data="sp_add", style="success"))
    if sponsors:
        b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data="sp_del_menu", style="danger"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    try: await c.message.edit_text(txt, reply_markup=b.as_markup())
    except Exception: pass
    await c.answer()

@dp.callback_query(F.data == "sp_add", IsAdminFilter())
async def sp_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("1️⃣ Введи название канала (как оно будет на кнопке):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_sp_name)
    await c.answer()

@dp.message(AdminStates.w_sp_name, IsAdminFilter())
async def sp_name(m: Message, state: FSMContext):
    await state.update_data(sp_name=m.text)
    await m.answer("2️⃣ Введи ссылку на канал (https://t.me/...):")
    await state.set_state(AdminStates.w_sp_url)

@dp.message(AdminStates.w_sp_url, IsAdminFilter())
async def sp_url(m: Message, state: FSMContext):
    if not m.text.startswith("http"):
        return await m.answer("❌ Ссылка должна начинаться с http:// или https://")
    await state.update_data(sp_url=m.text)
    await m.answer("3️⃣ Перешли ЛЮБОЙ пост из этого канала (чтобы я взял его ID):\n\n⚠️ <i>Не забудь добавить бота в админы канала!</i>")
    await state.set_state(AdminStates.w_sp_chat)

@dp.message(AdminStates.w_sp_chat, IsAdminFilter())
async def sp_chat(m: Message, state: FSMContext):
    chat_id = None
    if m.forward_origin and m.forward_origin.type == 'channel':
        chat_id = m.forward_origin.chat.id
    elif m.forward_from_chat:
        chat_id = m.forward_from_chat.id
        
    if not chat_id:
        return await m.answer("❌ Не могу получить ID. Убедись, что пересылаешь пост из канала (и у канала нет скрытых владельцев).")
        
    d = await state.get_data()
    db.add_sponsor(d['sp_name'], d['sp_url'], str(chat_id))
    await state.clear()
    await m.answer(f"✅ Спонсор <b>{d['sp_name']}</b> добавлен!", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "sp_del_menu", IsAdminFilter())
async def sp_del_menu(c: CallbackQuery):
    sponsors = db.get_sponsors()
    b = InlineKeyboardBuilder()
    for s in sponsors:
        b.row(InlineKeyboardButton(text=f"🗑 {s['name']}", callback_data=f"sp_del:{s['id']}", style="danger"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_sponsors"))
    await c.message.edit_text("Выбери спонсора для удаления:", reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("sp_del:"), IsAdminFilter())
async def sp_del(c: CallbackQuery):
    sid = int(c.data.split(":")[1])
    db.del_sponsor(sid)
    await c.answer("Удален")
    await admin_sponsors_menu(c)

# ================= АДМИНКА: ЗАЯВКИ =================
@dp.callback_query(F.data == "admin_wd", IsAdminFilter())
async def admin_wd(c: CallbackQuery):
    wds = db.get_pending_withdrawals()
    if not wds:
        return await c.message.edit_text("Нет активных заявок.", reply_markup=kb.back_admin_kb())
    
    w = wds[0]
    u = db.get_user(w['user_id'])
    uname = "@" + u['username'] if u['username'] else "id" + str(u['user_id'])
    
    txt = f"💸 <b>Заявка #{w['id']}</b>\n\n"
    txt += f"👤 Юзер: {uname} (<code>{u['user_id']}</code>)\n"
    txt += f"💰 Сумма: <b>{fmt(w['amount'])}</b> ⭐\n"
    txt += f"👥 Рефералов: {db.get_refs_count(u['user_id'])}\n"
    txt += f"🎯 Заданий: {u['tasks_completed']}\n"
    
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{w['id']}", style="success"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{w['id']}", style="danger")
    )
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    try: await c.message.edit_text(txt, reply_markup=b.as_markup())
    except Exception: pass
    await c.answer()

@dp.callback_query(F.data.startswith("wd_ok:"), IsAdminFilter())
async def wd_ok(c: CallbackQuery):
    wid = int(c.data.split(":")[1])
    db.set_withdrawal_status(wid, 'completed')
    w = db.get_withdrawal(wid)
    if w:
        try: await bot.send_message(w['user_id'], f"✅ Заявка #{wid} на {fmt(w['amount'])} ⭐ выплачена!")
        except Exception: pass
    await c.answer("Выплачено")
    await admin_wd(c)

@dp.callback_query(F.data.startswith("wd_no:"), IsAdminFilter())
async def wd_no(c: CallbackQuery):
    wid = int(c.data.split(":")[1])
    db.set_withdrawal_status(wid, 'rejected')
    w = db.get_withdrawal(wid)
    if w:
        db.add_balance(w['user_id'], w['amount'])
        try: await bot.send_message(w['user_id'], f"❌ Заявка #{wid} отклонена. Средства возвращены.")
        except Exception: pass
    await c.answer("Отклонено")
    await admin_wd(c)

# ================= АДМИНКА: ЮЗЕРЫ =================
@dp.callback_query(F.data == "admin_user", IsAdminFilter())
async def admin_user(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи ID или @username юзера:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_search)
    await c.answer()

@dp.message(AdminStates.w_u_search, IsAdminFilter())
async def admin_user_search(m: Message, state: FSMContext):
    q = m.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await m.answer("❌ Не найден.")
    
    uname = "@" + u['username'] if u['username'] else "—"
    txt = f"👤 <b>Профиль</b>\nID: <code>{u['user_id']}</code>\nНик: {uname}\nБаланс: {fmt(u['balance'])}⭐\nДолг: {fmt(u['debt'])}⭐\nЗаработал: {fmt(u['total_earned'])}⭐\nРефов: {db.get_refs_count(u['user_id'])}\nБан: {'Да' if u['is_banned'] else 'Нет'}"
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Разбанить" if u['is_banned'] else "🚫 Забанить", callback_data=f"u_ban:{u['user_id']}", style="success" if u['is_banned'] else "danger"))
    b.row(InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"u_bal:{u['user_id']}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    await m.answer(txt, reply_markup=b.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("u_ban:"), IsAdminFilter())
async def admin_user_ban(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    u = db.get_user(uid)
    db.toggle_ban(uid, 0 if u['is_banned'] else 1)
    await c.answer("Статус обновлен")
    # Перерисовываем профиль
    q = str(uid)
    await admin_user_search(Message(message_id=0, date=datetime.now(), chat=c.message.chat, from_user=c.from_user, text=q), None)

@dp.callback_query(F.data.startswith("u_bal:"), IsAdminFilter())
async def admin_user_bal(c: CallbackQuery, state: FSMContext):
    uid = int(c.data.split(":")[1])
    await state.update_data(bal_uid=uid)
    await c.message.edit_text("Введи сумму для изменения (например: 50 или -20):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)
    await c.answer()

@dp.message(AdminStates.w_u_bal, IsAdminFilter())
async def admin_user_bal_save(m: Message, state: FSMContext):
    try:
        amount = float(m.text)
        d = await state.get_data()
        db.add_balance(d['bal_uid'], amount)
        await m.answer(f"✅ Баланс изменен на {amount}⭐", reply_markup=kb.admin_kb())
        await state.clear()
    except Exception:
        await m.answer("Ошибка. Введи число.")

# ================= АДМИНКА: НАСТРОЙКИ =================
@dp.callback_query(F.data == "admin_settings", IsAdminFilter())
async def admin_settings(c: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"👥 Процент рефереру ({db.get_setting('ref_percent')}%)", callback_data="set:ref_percent"))
    b.row(InlineKeyboardButton(text=f"🎯 Награда за задание ({db.get_setting('task_reward')}⭐)", callback_data="set:task_reward"))
    b.row(InlineKeyboardButton(text=f"⚠️ Штраф за отписку ({db.get_setting('sponsor_penalty')}⭐)", callback_data="set:sponsor_penalty"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("set:"), IsAdminFilter())
async def admin_set_val(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[1]
    await state.update_data(set_key=key)
    await c.message.edit_text(f"Текущее значение <b>{key}</b>: {db.get_setting(key)}\n\nВведи новое значение:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await c.answer()

@dp.message(AdminStates.w_set_val, IsAdminFilter())
async def admin_set_save(m: Message, state: FSMContext):
    d = await state.get_data()
    db.set_setting(d['set_key'], m.text.strip())
    await m.answer("✅ Сохранено!", reply_markup=kb.admin_kb())
    await state.clear()

# ================= АДМИНКА: БЭКАП =================
@dp.callback_query(F.data == "admin_backup", IsAdminFilter())
async def admin_backup(c: CallbackQuery):
    txt = "📦 <b>Бэкап базы данных</b>\n\n"
    txt += "Чтобы <b>скачать</b> файл, нажми кнопку ниже (или напиши /backup).\n\n"
    txt += "Чтобы <b>загрузить</b> файл, просто отправь мне сюда файл базы данных (.db)."
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📥 Скачать файл", callback_data="backup_download", style="primary"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text(txt, reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data == "backup_download", IsAdminFilter())
async def backup_download(c: CallbackQuery):
    try:
        filename = "backup_" + datetime.now().strftime('%d_%m_%Y_%H_%M') + ".db"
        await c.message.answer_document(FSInputFile(DB, filename=filename), caption="💾 Бэкап БД")
    except Exception as e:
        await c.message.answer(f"Ошибка: {e}")
    await c.answer()

@dp.message(F.document, IsAdminFilter())
async def backup_upload(message: Message):
    if not message.document.file_name.endswith(".db"):
        return await message.answer("❌ Нужен файл с расширением .db")
    
    file_path = f"/tmp/{message.document.file_name}"
    await bot.download(message.document, destination=file_path)
    
    try:
        # Заменяем текущую базу
        shutil.copy(file_path, DB)
        await message.answer("✅ База данных успешно загружена и заменена!\n\n⚠️ <b>Внимание:</b> Зайди в панель BotHost и нажми «Обновить», чтобы бот перезагрузился с новой базой.")
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки: {e}")
        # ================= ВОРКЕР ПРОВЕРКИ ОТПИСОК =================
async def sponsor_check_worker():
    while True:
        await asyncio.sleep(3600) # Проверка каждый час (3600 секунд)
        try:
            sponsors = db.get_sponsors()
            if not sponsors: continue
            
            with db.get_conn() as conn:
                users = conn.execute("SELECT * FROM users").fetchall()
                
            for u in users:
                for s in sponsors:
                    try:
                        # Проверяем подписку через Telegram API
                        member = await bot.get_chat_member(s['chat_id'], u['user_id'])
                        if member.status in ['left', 'kicked']:
                            # Проверяем, получал ли он уже штраф (чтобы не списывать каждый час)
                            check = conn.execute("SELECT 1 FROM user_sponsors WHERE user_id=? AND sponsor_id=?", (u['user_id'], s['id'])).fetchone()
                            if check:
                                # Забираем из базы отметку, чтобы штраф не списывался снова
                                conn.execute("DELETE FROM user_sponsors WHERE user_id=? AND sponsor_id=?", (u['user_id'], s['id']))
                                conn.commit()
                                
                                penalty = float(db.get_setting("sponsor_penalty"))
                                if penalty > 0:
                                    # Штрафуем юзера
                                    db.add_balance(u['user_id'], -penalty)
                                    msg = f"❌ Вы отписались от канала <b>{s['name']}</b>. С вашего баланса списано {penalty} ⭐."
                                    try: await bot.send_message(u['user_id'], msg)
                                    except Exception: pass
                                    
                                    # Штрафуем реферера
                                    if u['referrer_id']:
                                        db.add_balance(u['referrer_id'], -penalty)
                                        ref_msg = f"⚠️ Ваш реферал @{u['username'] or u['user_id']} отписался от канала <b>{s['name']}</b>. С вашего баланса списано {penalty} ⭐."
                                        try: await bot.send_message(u['referrer_id'], ref_msg)
                                        except Exception: pass
                    except Exception:
                        pass
        except Exception as e:
            print(f"Ошибка воркера проверки спонсоров: {e}")

# ================= ЗАПУСК =================
async def main():
    db.init_db()
    asyncio.create_task(sponsor_check_worker())
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
