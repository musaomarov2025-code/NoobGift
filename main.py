import asyncio
import random
import re
from datetime import datetime, timedelta
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOT_TOKEN, ADMIN_ID, DB, DEFAULTS, WITHDRAW_AMOUNTS,
    BOTOHUB_TOKEN, BOTOHUB_URL, PIARFLOW_TOKEN, PIARFLOW_URL,
    TGRASS_TOKEN, TGRASS_URL, TRAFSLY_TOKEN, TRAFSLY_URL
)
import database as db
import keyboards as kb

if "menu_avatar" not in DEFAULTS:
    DEFAULTS["menu_avatar"] = ""

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

def _integration_on(name: str, role: str = None) -> bool:
    try:
        i = db.get_integration(name)
        if not i or i['status'] != 'on': return False
        if role and i['role'] != role: return False
        return True
    except Exception: return False

def fmt(amt):
    return f"{amt:.2f}".rstrip('0').rstrip('.') if amt % 1 else f"{amt:.0f}"

async def send_av(message, text, markup=None):
    av = db.get_setting("menu_avatar")
    if av: await message.answer_photo(photo=av, caption=text, reply_markup=markup)
    else: await message.answer(text=text, reply_markup=markup)

# ================== СОСТОЯНИЯ ==================
class AdminStates(StatesGroup):
    w_p_sum = State(); w_p_act = State(); w_p_srv = State(); w_p_cnt = State()
    w_u_search = State(); w_u_bal = State()
    w_ad_code = State(); w_ad_own = State(); w_ad_prc = State()
    w_int_key = State()
    w_bc_text = State(); w_bc_media = State(); w_bc_limit = State()
    w_set_val = State()

# ================== API СЕРВИСОВ ==================
async def get_bh_tasks(uid):
    token = db.get_integration('botohub')['api_key'] or BOTOHUB_TOKEN
    headers = {"Auth": token, "Content-Type": "application/json"}
    try: count = int(db.get_setting("botohub_entry_count") or 3)
    except: count = 3
    payload = {"chat_id": uid, "max_op": count}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(BOTOHUB_URL, json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    return [t for t in d.get("tasks", []) if not t.get("completed") and t.get("url")]
        except: pass
    return []

async def pf_get(uid):
    token = db.get_integration('piarflow')['api_key'] or PIARFLOW_TOKEN
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"user_id": uid, "chat_id": uid, "max_sponsors": 1}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(f"{PIARFLOW_URL}/sponsors", json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp: return {"srv": "piarflow", "tid": sp[0]["link"], "link": sp[0]["link"]}
        except: pass
    return None

async def pf_check(uid, tid):
    token = db.get_integration('piarflow')['api_key'] or PIARFLOW_TOKEN
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"user_id": uid, "links": [tid]}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{PIARFLOW_URL}/sponsors/check", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    return False

async def tg_get(uid):
    token = db.get_integration('tgrass')['api_key'] or TGRASS_TOKEN
    headers = {"Auth": token}
    payload = {"tg_user_id": uid, "is_premium": False, "lang": "ru"}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(TGRASS_URL, json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    off = d.get("offers", [])
                    if off and d.get("status") == "not_ok":
                        return {"srv": "tgrass", "tid": str(off[0]["offer_id"]), "link": off[0]["link"]}
        except: pass
    return None

async def tg_check(uid, tid):
    token = db.get_integration('tgrass')['api_key'] or TGRASS_TOKEN
    headers = {"Auth": token}
    payload = {"tg_user_id": uid, "offer_id": int(tid)}
    async with aiohttp.ClientSession() as s:
        async with s.post("https://tgrass.space/check", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("status") == "subscribed"
    return False

async def tr_get(uid):
    token = db.get_integration('trafsly')['api_key'] or TRAFSLY_TOKEN
    headers = {"Auth": token}
    payload = {"user_id": uid}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(TRAFSLY_URL, json=payload, headers=headers, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp and d.get("status") == "warning":
                        return {"srv": "trafsly", "tid": str(sp[0]["ads_id"]), "link": sp[0]["link"]}
        except: pass
    return None

async def tr_check(uid, tid):
    token = db.get_integration('trafsly')['api_key'] or TRAFSLY_TOKEN
    headers = {"Auth": token}
    payload = {"user_id": uid, "ads_id": tid}
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("subscribed") is True
    return False

async def get_new_task(uid):
    conn = db.get_conn()
    srv = conn.execute("SELECT name FROM integrations WHERE status = 'on' AND role = 'tasks'").fetchall()
    srv_names = [s['name'] for s in srv]
    conn.close()
    if "piarflow" in srv_names:
        t = await pf_get(uid)
        if t: return t
    if "tgrass" in srv_names:
        t = await tg_get(uid)
        if t: return t
    if "trafsly" in srv_names:
        t = await tr_get(uid)
        if t: return t
    return None

async def check_task_status(srv, uid, tid):
    if srv == "piarflow": return await pf_check(uid, tid)
    if srv == "tgrass": return await tg_check(uid, tid)
    if srv == "trafsly": return await tr_check(uid, tid)
    return False

# ================== СТАРТ И ОП ==================
@dp.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else None

    ref_id, promo_code, ad_code_val = None, None, None
    if payload:
        if payload.startswith("promo_"): promo_code = payload
        elif payload.startswith("ad_"): ad_code_val = payload[3:]
        elif payload.isdigit():
            ref_id = int(payload)
            if ref_id == uid: ref_id = None

    u = db.get_user(uid)
    if u and u['is_banned']: return await message.answer("🚫 Вы забанены в этом боте.")

    if db.add_user(uid, message.from_user.username, ref_id):
        if ref_id: db.create_pending_referral(uid, ref_id)
        if ad_code_val:
            db.track_ad_click(ad_code_val)
            db.set_user_ad_code(uid, ad_code_val)
    else: db.update_username(uid, message.from_user.username)

    if promo_code:
        ok, msg = db.activate_promo(promo_code, uid)
        if ok: await message.answer(msg)

    if db.get_setting("priv_enabled") == "1":
        await message.answer(db.get_setting("priv_text"))
        await asyncio.sleep(3)

    if _integration_on("botohub", "op"):
        op_tasks = await get_bh_tasks(uid)
        if op_tasks:
            kb_op = kb.op_screen_kb([(t.get('id', 0), "Подписаться", t['url'], False) for t in op_tasks])
            await message.answer(db.get_setting("botohub_text"), reply_markup=kb_op)
            return

    await finish_start(message, uid)

async def finish_start(message: Message, uid: int):
    db.set_op_passed(uid)
    ref = db.confirm_referral(uid)
    if ref:
        bns = float(db.get_setting("ref_bonus"))
        db.add_balance(ref, bns)
        try: await bot.send_message(ref, f'⭐ Твой реферал прошел ОП: <b>+{fmt(bns)} ⭐</b>')
        except: pass
    await send_main_menu(message)

@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery):
    if not _integration_on("botohub", "op"):
        await finish_start(call.message, call.from_user.id)
        return await call.answer()
    op_tasks = await get_bh_tasks(call.from_user.id)
    if not op_tasks:
        try: await call.message.delete()
        except: pass
        await finish_start(call.message, call.from_user.id)
        await call.answer()
    else: await call.answer("Вы подписались не на все каналы!", show_alert=True)

async def send_main_menu(message: Message):
    t = db.get_setting("menu_text").format(ref_bonus=db.get_setting("ref_bonus"))
    await send_av(message, t, kb.main_menu_kb())

@dp.callback_query(F.data == "menu_back")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except: pass
    await send_main_menu(call.message)
    await call.answer()

# ================== ЗАДАНИЯ ==================
@dp.callback_query(F.data == "menu_earn")
async def show_tasks(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, call.from_user.id)
    await call.answer()

async def send_next_task(message: Message, uid: int):
    task = db.get_pending_task(uid)
    if not task:
        new_t = await get_new_task(uid)
        if not new_t:
            return await message.answer("😔 На данный момент нет доступных заданий.", reply_markup=kb.back_kb())
        db.save_task(uid, new_t["srv"], new_t["tid"], new_t["link"])
        task = db.get_pending_task(uid)
    t = db.get_setting("task_text").format(reward=db.get_setting("task_reward"))
    await message.answer(t, reply_markup=kb.task_kb(task["link"]))

@dp.callback_query(F.data == "check_task")
async def check_task_cb(call: CallbackQuery):
    uid = call.from_user.id
    task = db.get_pending_task(uid)
    if not task: return await call.answer("Задание не найдено.", show_alert=True)
    await call.message.edit_text("⏳ Проверяем...")
    is_done = await check_task_status(task['service'], uid, task['task_id'])
    if is_done:
        reward = float(db.get_setting("task_reward"))
        db.add_balance(uid, reward)
        db.mark_task_completed(uid, task['service'], task['task_id'], reward)
        db.mark_task_status(task['id'], 'done')
        await call.message.edit_text(f"✅ Выполнено! Начислено: {fmt(reward)} ⭐")
        await asyncio.sleep(1.5)
        try: await call.message.delete()
        except: pass
        await send_next_task(call.message, uid)
    else: await call.message.edit_text("❌ Не выполнено.", reply_markup=kb.task_kb(task["link"]))
    await call.answer()

@dp.callback_query(F.data == "skip_task")
async def skip_task_cb(call: CallbackQuery):
    task = db.get_pending_task(call.from_user.id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено", show_alert=True)
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, call.from_user.id)

# ================== ПРОФИЛЬ, РЕФЕРАЛЫ, СТАТИСТИКА ==================
@dp.callback_query(F.data == "menu_profile")
async def menu_profile(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    t = db.get_setting("profile_text").format(
        username=f"@{u['username']}" if u['username'] else "Юзер", 
        total_refs=db.get_pending_refs_count(u['user_id'])+db.get_confirmed_refs_count(u['user_id']), 
        total_earned=fmt(u['total_earned']), balance=fmt(u['balance']), user_id=u['user_id'], tasks_completed=u['tasks_completed']
    )
    await send_av(call.message, t, kb.back_kb())

@dp.callback_query(F.data == "menu_refs")
async def menu_refs(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    uid = call.from_user.id; u = db.get_user(uid); me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={uid}"
    refs = db.get_user_referrals(uid)
    txt = "".join([f"├ @{r['username'] or 'id'+str(r['user_id'])} — {'Ожидает' if r['status']=='pending' else '✅'}\n" for r in refs]) or "├ Пока никого нет\n"
    t = db.get_setting("ref_text").format(
        ref_bonus=db.get_setting("ref_bonus"), ref_link=link, 
        total_refs=db.get_pending_refs_count(uid)+db.get_confirmed_refs_count(uid), 
        confirmed_refs=db.get_confirmed_refs_count(uid), ref_list=txt, balance=fmt(u['balance'])
    )
    await send_av(call.message, t, kb.back_kb())

@dp.callback_query(F.data == "menu_instruction")
async def menu_instruction(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    await send_av(call.message, db.get_setting("instruction_text"), kb.back_kb())

@dp.callback_query(F.data == "menu_stats")
async def menu_stats(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    s = db.get_stats()
    t = db.get_setting("stats_text").format(total_users=s['total'], total_withdrawn=fmt(s['total_stars']))
    await send_av(call.message, t, kb.stats_kb())

@dp.callback_query(F.data == "top_balance")
async def top_balance(call: CallbackQuery):
    users = db.get_top_balance()
    txt = "🏆 <b>Топ по балансу</b>\n\n"
    for i, u in enumerate(users, 1):
        txt += f"{i}. @{u['username'] or 'id'+str(u['user_id'])} — <b>{fmt(u['balance'])}</b> ⭐\n"
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

@dp.callback_query(F.data == "top_refs")
async def top_refs(call: CallbackQuery):
    users = db.get_top_refs()
    txt = "🏆 <b>Топ по рефералам</b>\n\n"
    for i, u in enumerate(users, 1):
        txt += f"{i}. @{u['username'] or 'id'+str(u['user_id'])} — <b>{u['refs']}</b> чел.\n"
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

@dp.callback_query(F.data == "top_earn")
async def top_earn(call: CallbackQuery):
    with db.get_conn() as conn:
        users = conn.execute("SELECT user_id, username, total_earned FROM users ORDER BY total_earned DESC LIMIT 10").fetchall()
    txt = "🏆 <b>Топ по заработку</b>\n\n"
    for i, u in enumerate(users, 1):
        txt += f"{i}. @{u['username'] or 'id'+str(u['user_id'])} — <b>{fmt(u['total_earned'])}</b> ⭐\n"
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

# ================== ВЫВОД ==================
@dp.callback_query(F.data == "menu_withdraw")
async def menu_withdraw(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    req_friends = int(db.get_setting("withdraw_friends_required"))
    conf_friends = db.get_confirmed_refs_count(u['user_id'])
    t = db.get_setting("withdraw_text").format(balance=fmt(u['balance']), amounts=", ".join(map(str, WITHDRAW_AMOUNTS)))
    if conf_friends < req_friends:
        t += f"\n\n⚠️ <b>Внимание!</b> Для вывода нужно пригласить минимум <b>{req_friends}</b> друзей (у тебя {conf_friends})."
    await send_av(call.message, t, kb.withdraw_kb())

@dp.callback_query(F.data.regexp(r"^wd_\d+$"))
async def process_wd(call: CallbackQuery):
    amount = float(call.data.split("_")[1])
    u = db.get_user(call.from_user.id)
    if amount not in WITHDRAW_AMOUNTS: return await call.answer("Неверная сумма", show_alert=True)
    if u['balance'] < amount: return await call.answer(f"Не хватает! Баланс: {fmt(u['balance'])}", show_alert=True)
    req = int(db.get_setting("withdraw_friends_required"))
    if db.get_confirmed_refs_count(u['user_id']) < req: return await call.answer(f"Нужно пригласить друзей: {req}", show_alert=True)
    wid = db.create_withdrawal(u['user_id'], amount)
    await call.message.edit_text(f'✅ Заявка <b>#{wid}</b> на <b>{fmt(amount)}</b> ⭐ создана.\n\nОжидайте подтверждения.', reply_markup=kb.back_kb())
    await call.answer()

# ================== АДМИНКА: БАЗА ==================
@dp.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "admin_back", StateFilter("*"))
async def admin_back_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())
    await call.answer()

# ================== АДМИНКА: ЗАЯВКИ ==================
@dp.callback_query(F.data == "wd_list")
async def admin_wd_list(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    if not wds: return await call.message.edit_text("Нет активных заявок.", reply_markup=kb.wd_empty_kb())
    await show_wd_page(call, 0)

async def show_wd_page(call: CallbackQuery, idx: int):
    wds = db.get_pending_withdrawals()
    if not wds: return await call.message.edit_text("Заявок больше нет.", reply_markup=kb.wd_empty_kb())
    idx = max(0, min(idx, len(wds)-1))
    w = wds[idx]; u = db.get_user(w['user_id'])
    refs = db.get_confirmed_refs_count(u['user_id']); tasks = u['tasks_completed']
    reg_date = u['registered_at'][:10] if u['registered_at'] else "—"
    txt = (f"💸 <b>Заявка #{w['id']}</b>\n\n👤 Юзер: @{u['username'] or 'id'+str(u['user_id'])} (<code>{u['user_id']}</code>)\n"
           f"💰 Сумма: <b>{fmt(w['amount'])}</b> ⭐\n📅 Регистрация: {reg_date}\n\n"
           f"📊 <b>Аналитика:</b>\n├ Друзей: {refs}\n├ Заданий: {tasks}\n└ Заработал всего: {fmt(u['total_earned'])} ⭐")
    await call.message.edit_text(txt, reply_markup=kb.wd_page_kb(w['id'], idx, len(wds)))

@dp.callback_query(F.data.startswith("wd_page:"))
async def wd_page_nav(call: CallbackQuery): await show_wd_page(call, int(call.data.split(":")[1]))

@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    wid = int(call.data.split(":")[1]); db.set_withdrawal_status(wid, 'completed')
    w = db.get_withdrawal(wid)
    if w:
        try: await bot.send_message(w['user_id'], f"✅ Твоя заявка на вывод <b>{fmt(w['amount'])}</b> ⭐ одобрена!")
        except: pass
    await call.answer("Одобрено!"); await show_wd_page(call, 0)

@dp.callback_query(F.data.startswith("wd_no:"))
async def wd_no(call: CallbackQuery):
    wid = int(call.data.split(":")[1]); db.set_withdrawal_status(wid, 'rejected')
    w = db.get_withdrawal(wid)
    if w:
        db.add_balance(w['user_id'], w['amount'])
        try: await bot.send_message(w['user_id'], f"❌ Заявка на вывод отклонена. Средства возвращены на баланс.")
        except: pass
    await call.answer("Отклонено"); await show_wd_page(call, 0)

@dp.callback_query(F.data == "wd_accept_all")
async def wd_accept_all(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    for w in wds:
        db.set_withdrawal_status(w['id'], 'completed')
        try: await bot.send_message(w['user_id'], f"✅ Твоя заявка на вывод <b>{fmt(w['amount'])}</b> ⭐ одобрена!")
        except: pass
    await call.message.edit_text("✅ Все заявки одобрены.", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "wd_reject_all")
async def wd_reject_all(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    for w in wds:
        db.set_withdrawal_status(w['id'], 'rejected'); db.add_balance(w['user_id'], w['amount'])
        try: await bot.send_message(w['user_id'], f"❌ Заявка отклонена. Средства возвращены.")
        except: pass
    await call.message.edit_text("❌ Все заявки отклонены.", reply_markup=kb.back_admin_kb())

# ================== АДМИНКА: ПОИСК И НАЧИСЛЕНИЕ ==================
@dp.callback_query(F.data == "user_find")
async def admin_fu(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введи ID или @username:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_search)

@dp.message(AdminStates.w_u_search)
async def search_user(message: Message, state: FSMContext):
    q = message.text.strip(); u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await message.answer("❌ Не найден.")
    refs = db.get_confirmed_refs_count(u['user_id']); reg = u['registered_at'][:10] if u['registered_at'] else "—"
    t = (f"👤 <b>Профиль</b>\nID: <code>{u['user_id']}</code>\nНик: @{u['username'] or '—'}\nРега: {reg}\n"
         f"Баланс: <b>{fmt(u['balance'])}</b> ⭐\nЗаработал: <b>{fmt(u['total_earned'])}</b>\n"
         f"Заданий: <b>{u['tasks_completed']}</b>\nДрузей: <b>{refs}</b>\nБан: {'Да' if u['is_banned'] else 'Нет'}")
    await message.answer(t, reply_markup=kb.user_action_kb(u['user_id'], u['is_banned']))
    await state.clear()

@dp.callback_query(F.data.startswith("u_ban:"))
async def user_ban(call: CallbackQuery):
    uid = int(call.data.split(":")[1]); u = db.get_user(uid); new_status = 0 if u['is_banned'] else 1
    db.toggle_ban(uid, new_status); await call.answer("Статус обновлен")
    refs = db.get_confirmed_refs_count(u['user_id']); reg = u['registered_at'][:10] if u['registered_at'] else "—"
    t = (f"👤 <b>Профиль</b>\nID: <code>{u['user_id']}</code>\nНик: @{u['username'] or '—'}\nРега: {reg}\n"
         f"Баланс: <b>{fmt(u['balance'])}</b> ⭐\nЗаработал: <b>{fmt(u['total_earned'])}</b>\n"
         f"Заданий: <b>{u['tasks_completed']}</b>\nДрузей: <b>{refs}</b>\nБан: {'Да' if new_status else 'Нет'}")
    await call.message.edit_text(t, reply_markup=kb.user_action_kb(uid, new_status))

@dp.callback_query(F.data.startswith("u_bal:"))
async def user_bal(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split(":")[1]); await state.update_data(bal_uid=uid, give_mode=False)
    await call.message.edit_text("Введи сумму (например 50 или -20):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)

@dp.callback_query(F.data == "give_start")
async def give_start(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи ID юзера для начисления:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal); await state.update_data(bal_uid=None, give_mode=True)

@dp.message(AdminStates.w_u_bal)
async def save_bal_or_give(message: Message, state: FSMContext):
    d = await state.get_data()
    if d.get('give_mode') and d.get('bal_uid') is None:
        try:
            uid = int(message.text.strip()); u = db.get_user(uid)
            if not u: return await message.answer("❌ Юзер не найден.")
            await state.update_data(bal_uid=uid)
            await message.answer(f"Юзер: @{u['username'] or 'id'+str(uid)}\nВведи сумму начисления:")
        except: await message.answer("Ошибка. Введи числовой ID.")
    else:
        try:
            a = float(message.text); db.add_balance(d['bal_uid'], a)
            await message.answer("✅ Баланс изменен!", reply_markup=kb.back_admin_kb()); await state.clear()
        except: await message.answer("Ошибка. Введи число.")

# ================== АДМИНКА: ПРОМОКОДЫ ==================
@dp.callback_query(F.data == "promos")
async def admin_promos(c: CallbackQuery): await c.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=kb.promos_kb())

@dp.callback_query(F.data == "promo_list")
async def promo_list(c: CallbackQuery):
    promos = db.get_all_promos()
    if not promos: return await c.message.edit_text("Нет промокодов.", reply_markup=kb.back_admin_kb())
    txt = "📜 <b>Список промокодов:</b>\n\n"
    for p in promos: txt += f"<code>{p['code']}</code> | {p['amount']} ⭐ | {p['used']}/{p['max_uses']} | ОП: {'Да' if p['is_op'] else 'Нет'}\n"
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "promo_create")
async def promo_create(c: CallbackQuery, state: FSMContext):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Обычный", callback_data="p_type:0"))
    b.row(InlineKeyboardButton(text="С ОП", callback_data="p_type:1"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="promos"))
    await c.message.edit_text("Выбери тип промокода:", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("p_type:"))
async def promo_type(c: CallbackQuery, state: FSMContext):
    await state.update_data(is_op=int(c.data.split(":")[1]))
    await c.message.edit_text("Введи сумму чека (звезды):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_p_sum)

@dp.message(AdminStates.w_p_sum)
async def promo_sum(m: Message, state: FSMContext):
    try:
        await state.update_data(p_amount=float(m.text)); await m.answer("Сколько активаций (лимит)?")
        await state.set_state(AdminStates.w_p_act)
    except: await m.answer("Ошибка. Введи число.")

@dp.message(AdminStates.w_p_act)
async def promo_act(m: Message, state: FSMContext):
    try:
        await state.update_data(p_uses=int(m.text)); d = await state.get_data()
        if d['is_op']:
            await m.answer("Какой сервис? (botohub, piarflow, tgrass, trafsly):")
            await state.set_state(AdminStates.w_p_srv)
        else:
            code = "promo_" + str(random.randint(100000, 999999))
            db.create_promo(code, d['p_amount'], d['p_uses'], is_op=0)
            me = await bot.get_me()
            await m.answer(f"✅ Чек создан!\nСсылка: https://t.me/{me.username}?start={code}", reply_markup=kb.back_admin_kb())
            await state.clear()
    except: await m.answer("Ошибка. Введи число.")

@dp.message(AdminStates.w_p_srv)
async def promo_srv(m: Message, state: FSMContext):
    await state.update_data(p_srv=m.text.lower()); await m.answer("Сколько спонсоров пройти?")
    await state.set_state(AdminStates.w_p_cnt)

@dp.message(AdminStates.w_p_cnt)
async def promo_cnt(m: Message, state: FSMContext):
    try:
        d = await state.get_data(); cnt = int(m.text)
        code = "promo_op_" + str(random.randint(100000, 999999))
        db.create_promo(code, d['p_amount'], d['p_uses'], is_op=1, op_service=d['p_srv'], op_count=cnt)
        me = await bot.get_me()
        await m.answer(f"✅ Чек с ОП создан!\nСсылка: https://t.me/{me.username}?start={code}", reply_markup=kb.back_admin_kb())
        await state.clear()
    except: await m.answer("Ошибка.")

# ================== АДМИНКА: РЕКЛАМА ==================
@dp.callback_query(F.data == "ad_menu")
async def admin_ads(c: CallbackQuery): await c.message.edit_text("📊 <b>Реклама</b>", reply_markup=kb.ad_menu_kb())

@dp.callback_query(F.data == "ad_list")
async def ad_list(c: CallbackQuery):
    ads = db.get_all_ads()
    if not ads: return await c.message.edit_text("Нет меток.", reply_markup=kb.back_admin_kb())
    txt = "📜 <b>Список меток:</b>\n\n"
    for a in ads: txt += f"<code>{a['code']}</code> | Кликов: {a['clicks']} | Цена: {a['price']}₽\nСтата: <code>/stat_{a['code']}</code>\n\n"
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "ad_add")
async def ad_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи код метки (например tiktok):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_ad_code)

@dp.message(AdminStates.w_ad_code)
async def ad_code(m: Message, state: FSMContext):
    await state.update_data(ad_code=m.text.lower()); await m.answer("Введи ID или @username рекламодателя:")
    await state.set_state(AdminStates.w_ad_own)

@dp.message(AdminStates.w_ad_own)
async def ad_own(m: Message, state: FSMContext):
    q = m.text.strip(); u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await m.answer("Не найден.")
    await state.update_data(ad_own=u['user_id']); await m.answer("Введи цену за переход (в рублях):")
    await state.set_state(AdminStates.w_ad_prc)

@dp.message(AdminStates.w_ad_prc)
async def ad_prc(m: Message, state: FSMContext):
    try:
        d = await state.get_data(); prc = float(m.text)
        db.add_ad_source(d['ad_code'], d['ad_own'], prc); me = await bot.get_me()
        await m.answer(f"✅ Метка создана!\nСсылка: https://t.me/{me.username}?start=ad_{d['ad_code']}\nСтата: /stat_{d['ad_code']}", reply_markup=kb.back_admin_kb())
        await state.clear()
    except: await m.answer("Ошибка. Введи число.")

@dp.message(F.text.startswith("/stat_"))
async def ad_stat_cmd(m: Message):
    code = m.text.split("_", 1)[1].lower(); text, b = await _build_ad_stat(code)
    if not text: return await m.answer("❌ Метка не найдена.")
    await m.answer(text, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("upd_stat:"))
async def upd_stat(c: CallbackQuery):
    code = c.data.split(":", 1)[1]; text, b = await _build_ad_stat(code)
    if not text: return await c.answer("Не найдено", show_alert=True)
    await c.message.edit_text(text, reply_markup=b.as_markup()); await c.answer("Обновлено")

async def _build_ad_stat(code: str):
    src = db.get_ad_source(code)
    if not src: return None, None
    conn = db.get_conn()
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ?", (code,)).fetchone()[0]
    passed_op = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ? AND passed_op = 1", (code,)).fetchone()[0]
    tasks = conn.execute("SELECT COUNT(*) FROM task_completed tc JOIN users u ON tc.user_id = u.user_id WHERE u.ad_code = ?", (code,)).fetchone()[0]
    earned = conn.execute("SELECT SUM(balance) FROM users WHERE ad_code = ?", (code,)).fetchone()[0] or 0.0
    withdrawn = conn.execute("SELECT SUM(amount) FROM withdrawals w JOIN users u ON w.user_id = u.user_id WHERE u.ad_code = ? AND w.status = 'completed'", (code,)).fetchone()[0] or 0.0
    conn.close()
    text = (f"📊 <b>Статистика метки: {code}</b>\n\n👤 Переходов: <b>{src['clicks']}</b>\n🆕 Зарегалось: <b>{total_users}</b>\n"
            f"✅ Прошли ОП: <b>{passed_op}</b>\n🎯 Заданий выполнено: <b>{tasks}</b>\n💰 Заработали: <b>{fmt(earned)}</b> ⭐\n"
            f"💸 Вывели: <b>{fmt(withdrawn)}</b> ⭐\n\n💵 Цена перехода: <b>{src['price']} ₽</b>\n👤 Рекламодатель: <code>{src['owner_id']}</code>")
    b = InlineKeyboardBuilder(); b.row(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"upd_stat:{code}"))
    return text, b

# ================== АДМИНКА: ИНТЕГРАЦИИ ==================
@dp.callback_query(F.data == "tasks_menu")
async def admin_ints(call: CallbackQuery):
    b = InlineKeyboardBuilder()
    for i in db.get_all_integrations():
        s = "🟢" if i['status'] == 'on' else "🔴"
        b.row(InlineKeyboardButton(text=f"{s} {i['name'].upper()} ({'ОП' if i['role']=='op' else 'Задания'})", callback_data=f"int_view:{i['name']}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await call.message.edit_text("🔌 <b>Интеграции и Сервисы</b>\nНастрой API и роли:", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("int_view:"))
async def int_view(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 Выкл" if i['status'] == 'on' else "🟢 Вкл", callback_data=f"int_toggle:{n}"))
    b.row(InlineKeyboardButton(text="Сменить роль (ОП/Задания)", callback_data=f"int_role:{n}"))
    b.row(InlineKeyboardButton(text="🔑 Сменить API Ключ", callback_data=f"int_key:{n}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="tasks_menu"))
    await call.message.edit_text(f"⚙️ <b>{n.upper()}</b>\nРоль: {i['role']}\nКлюч: {i['api_key'] or 'По умолчанию'}", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("int_toggle:"))
async def int_toggle(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.toggle_integration(n, 'off' if i['status'] == 'on' else 'on'); await int_view(call)

@dp.callback_query(F.data.startswith("int_role:"))
async def int_role(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.set_integration_role(n, 'tasks' if i['role'] == 'op' else 'op'); await int_view(call)

@dp.callback_query(F.data.startswith("int_key:"))
async def int_key(call: CallbackQuery, state: FSMContext):
    n = call.data.split(":")[1]; await state.update_data(int_name=n)
    await call.message.edit_text(f"Введи ключ для {n.upper()}:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_int_key)

@dp.message(AdminStates.w_int_key)
async def save_int_key(message: Message, state: FSMContext):
    d = await state.get_data(); db.update_integration_key(d['int_name'], message.text.strip())
    await state.clear(); await message.answer("✅ Ключ сохранен!", reply_markup=kb.back_admin_kb())

# ================== АДМИНКА: НАСТРОЙКИ ==================
@dp.callback_query(F.data == "settings")
async def admin_settings(c: CallbackQuery): await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=kb.settings_kb())

@dp.callback_query(F.data.startswith("set:"))
async def set_val(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[1]; await state.update_data(set_key=key)
    await c.message.edit_text(f"Текущее значение <b>{key}</b>: {db.get_setting(key)}\n\nВведи новое значение:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)

@dp.message(AdminStates.w_set_val)
async def save_set(m: Message, state: FSMContext):
    d = await state.get_data(); db.set_setting(d['set_key'], m.text.strip())
    await m.answer("✅ Настройка сохранена!", reply_markup=kb.back_admin_kb()); await state.clear()

# ================== ЗАПЛАТКА: ДОП. КНОПКИ АДМИНКИ ==================
@dp.callback_query(F.data == "stats")
async def admin_detailed_stats(c: CallbackQuery):
    s = db.get_stats()
    txt = (f"📊 <b>Статистика бота</b>\n\n👥 Всего юзеров: <b>{s['total']}</b>\n🆕 За сегодня: <b>{s['today']}</b>\n"
           f"💰 Общий баланс: <b>{fmt(s['total_balance'])}</b> ⭐\n\n📥 Заявок в ожидании: <b>{s['pending']}</b>\n"
           f"✅ Всего выведено: <b>{s['done']}</b> заявок\n💸 Сумма выводов: <b>{fmt(s['total_stars'])}</b> ⭐")
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb()); await c.answer()

@dp.callback_query(F.data == "priv_menu")
async def admin_priv(c: CallbackQuery):
    status = "🟢 Включена" if db.get_setting("priv_enabled") == "1" else "🔴 Выключена"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 Выкл" if db.get_setting("priv_enabled") == "1" else "🟢 Вкл", callback_data="priv_toggle"))
    b.row(InlineKeyboardButton(text="✏️ Изменить текст", callback_data="priv_edit_text"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text(f"🎛 <b>Приватка</b>\n\nСтатус: {status}\n\nТекст:\n{db.get_setting('priv_text') or '—'}", reply_markup=b.as_markup())

@dp.callback_query(F.data == "priv_toggle")
async def priv_toggle(c: CallbackQuery):
    cur = db.get_setting("priv_enabled"); db.set_setting("priv_enabled", "0" if cur == "1" else "1")
    await admin_priv(c)

@dp.callback_query(F.data == "priv_edit_text")
async def priv_edit(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь новый текст приватки (HTML):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val); await state.update_data(set_key="priv_text")

@dp.callback_query(F.data == "bh_menu")
async def admin_bh(c: CallbackQuery):
    en = db.get_setting("botohub_enabled") == "1"
    await c.message.edit_text(f"🎯 <b>ОП (Botohub)</b>\n\nСтатус: {'🟢 Вкл' if en else '🔴 Выкл'}\nКол-во на входе: <b>{db.get_setting('botohub_entry_count')}</b>\n\n<i>Все ключи и вкл/выкл настраиваются в разделе «Задания (Сервисы)».</i>", reply_markup=kb.bh_kb(en))

@dp.callback_query(F.data == "bh_toggle")
async def bh_toggle(c: CallbackQuery):
    cur = db.get_setting("botohub_enabled"); db.set_setting("botohub_enabled", "0" if cur == "1" else "1")
    await admin_bh(c)

@dp.callback_query(F.data == "bh_edit_text")
async def bh_edit_text(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь новый текст для ОП:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val); await state.update_data(set_key="botohub_text")

@dp.callback_query(F.data == "bh_edit_entry")
async def bh_edit_entry(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Сколько каналов показывать при входе?", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val); await state.update_data(set_key="botohub_entry_count")

# ================== АДМИНКА: РАССЫЛКА ==================
BC_STATE = {"text": "", "media": None, "media_type": None, "limit": 0}

@dp.callback_query(F.data == "broadcast_menu")
async def bc_menu(c: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Текст", callback_data="bc_edit_text"))
    b.row(InlineKeyboardButton(text="📎 Медиа", callback_data="bc_edit_media"))
    b.row(InlineKeyboardButton(text="🔢 Лимит юзеров (0 = все)", callback_data="bc_edit_limit"))
    b.row(InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bc_preview"))
    b.row(InlineKeyboardButton(text="✅ Отправить", callback_data="bc_start"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("📢 <b>Умная рассылка</b>", reply_markup=b.as_markup())

@dp.callback_query(F.data == "bc_edit_text")
async def bc_edit_text(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь текст (HTML):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_text)

@dp.message(AdminStates.w_bc_text)
async def bc_save_text(m: Message, state: FSMContext):
    BC_STATE['text'] = m.html_text; await m.answer("✅ Текст сохранен!", reply_markup=kb.back_admin_kb()); await state.clear()

@dp.callback_query(F.data == "bc_edit_media")
async def bc_edit_media(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь фото или видео:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_media)

@dp.message(AdminStates.w_bc_media)
async def bc_save_media(m: Message, state: FSMContext):
    if m.photo: BC_STATE['media'] = m.photo[-1].file_id; BC_STATE['media_type'] = 'photo'
    elif m.video: BC_STATE['media'] = m.video.file_id; BC_STATE['media_type'] = 'video'
    else: return await m.answer("Нужно фото или видео.")
    await m.answer("✅ Медиа сохранено!", reply_markup=kb.back_admin_kb()); await state.clear()

@dp.callback_query(F.data == "bc_edit_limit")
async def bc_edit_limit(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Сколько юзеров обработать? (0 = все):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_limit)

@dp.message(AdminStates.w_bc_limit)
async def bc_save_limit(m: Message, state: FSMContext):
    try: BC_STATE['limit'] = int(m.text); await m.answer(f"✅ Лимит: {BC_STATE['limit']}", reply_markup=kb.back_admin_kb())
    except: await m.answer("Ошибка. Введи число.")
    await state.clear()

@dp.callback_query(F.data == "bc_preview")
async def bc_preview(c: CallbackQuery):
    text, media, mtype = BC_STATE.get('text', ''), BC_STATE.get('media'), BC_STATE.get('media_type')
    if not text and not media: return await c.answer("Пусто", show_alert=True)
    if media:
        if mtype == 'photo': await c.message.answer_photo(media, caption=text)
        else: await c.message.answer_video(media, caption=text)
    else: await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data == "bc_start")
async def bc_start(c: CallbackQuery):
    if not BC_STATE.get('text') and not BC_STATE.get('media'):
        return await c.answer("Сначала задай текст или медиа!", show_alert=True)
    conn = db.get_conn(); users = conn.execute("SELECT user_id FROM users").fetchall(); conn.close()
    limit = BC_STATE.get('limit', 0)
    if limit > 0: users = users[:limit]
    await c.message.edit_text(f"⏳ Рассылка для {len(users)} юзеров...")
    text, media, mtype, ok, err = BC_STATE.get('text', ''), BC_STATE.get('media'), BC_STATE.get('media_type'), 0, 0
    for u in users:
        try:
            if media:
                if mtype == 'photo': await c.bot.send_photo(u['user_id'], media, caption=text)
                else: await c.bot.send_video(u['user_id'], media, caption=text)
            else: await c.bot.send_message(u['user_id'], text)
            ok += 1; await asyncio.sleep(0.05)
        except: err += 1
    await c.message.answer(f"✅ Готово.\nУспешно: {ok}\nОшибок: {err}", reply_markup=kb.back_admin_kb())
    BC_STATE.clear(); BC_STATE.update({"text": "", "media": None, "media_type": None, "limit": 0})

# ================== БЭКАП И ЗАПУСК ==================
@dp.callback_query(F.data == "backup_help")
async def admin_backup(c: CallbackQuery):
    try:
        doc = FSInputFile(DB); await c.message.answer_document(doc, caption="💾 Бэкап БД")
    except Exception as e: await c.message.answer(f"Ошибка: {e}")
    await c.answer()

async def daily_backup_worker():
    while True:
        try:
            now = datetime.now()
            targets = [now.replace(hour=8, minute=0, second=0, microsecond=0), now.replace(hour=20, minute=0, second=0, microsecond=0)]
            next_run = next((t for t in targets if t > now), targets[0] + timedelta(days=1))
            await asyncio.sleep((next_run - now).total_seconds())
            doc = FSInputFile(DB); await bot.send_document(ADMIN_ID, doc, caption=f"📦 <b>Авто-бэкап</b>\n{datetime.now().strftime('%d.%m.%Y %H:%M')}")
        except Exception as e:
            print(f"Ошибка бэкапа: {e}"); await asyncio.sleep(3600)

async def main():
    db.init_db()
    asyncio.create_task(daily_backup_worker())
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
