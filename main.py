import asyncio
import logging
import random
import re
import json
from datetime import datetime, timedelta
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter, BaseFilter
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
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
    await message.answer(text=text, reply_markup=markup)

class UserStates(StatesGroup):
    w_amount = State()

class AdminStates(StatesGroup):
    w_p_sum = State(); w_p_act = State(); w_p_srv = State(); w_p_cnt = State()
    w_u_search = State(); w_u_bal = State()
    w_ad_code = State(); w_ad_own = State(); w_ad_prc = State()
    w_int_key = State(); w_bc_text = State(); w_bc_media = State(); w_bc_limit = State(); w_bc_btn_bulk = State()
    w_set_val = State(); w_priv_btn_bulk = State(); w_admin_add = State()
    w_sn_text = State(); w_sn_media = State(); w_sn_btn = State(); w_sn_interval = State()

# ================= API =================
async def pf_get(uid):
    token = db.get_integration('piarflow')['api_key'] or PIARFLOW_TOKEN
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
    token = db.get_integration('piarflow')['api_key'] or PIARFLOW_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{PIARFLOW_URL}/sponsors/check", json={"user_id": uid, "links": [tid]}, headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    return False

async def tg_get(uid):
    token = db.get_integration('tgrass')['api_key'] or TGRASS_TOKEN
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
    token = db.get_integration('tgrass')['api_key'] or TGRASS_TOKEN
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://tgrass.space/check", json={"tg_user_id": uid, "offer_id": int(tid)}, headers={"Auth": token}, timeout=10) as r:
                if r.status != 200: return False
                d = await r.json()
                if d.get("status") == "subscribed": return True
        except Exception: pass
    return False

async def tr_get(uid):
    token = db.get_integration('trafsly')['api_key'] or TRAFSLY_TOKEN
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
    token = db.get_integration('trafsly')['api_key'] or TRAFSLY_TOKEN
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json={"user_id": uid, "ads_id": tid}, headers={"Auth": token}) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("subscribed") is True
    return False

async def sg_get(uid):
    token = db.get_integration('subgram')['api_key']
    if not token: return None
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://api.subgram.org/get-sponsors", json={"user_id": uid, "chat_id": uid, "max_sponsors": 1, "get_links": 1}, headers={"Auth": token}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "warning" and d.get("sponsors"): return {"srv": "subgram", "tid": d["sponsors"][0]["resource_id"], "link": d["sponsors"][0]["link"]}
        except Exception: pass
    return None

async def sg_check(uid, tid):
    token = db.get_integration('subgram')['api_key']
    if not token: return False
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://api.subgram.org/get-sponsors", json={"user_id": uid, "chat_id": uid, "max_sponsors": 10, "get_links": 1}, headers={"Auth": token}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "ok": return True
                    for sp in d.get("sponsors", []):
                        if str(sp["resource_id"]) == str(tid): return False
                    return True
        except Exception: pass
    return False

async def fl_get(uid):
    token = db.get_integration('flyer')['api_key']
    if not token: return None
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://api.flyerhubs.com/get_tasks", json={"key": token, "user_id": uid}, headers={"Content-Type": "application/json"}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    tasks = d.get("tasks", [])
                    if tasks: return {"srv": "flyer", "tid": tasks[0]["signature"], "link": tasks[0]["link"]}
        except Exception: pass
    return None

async def fl_check(uid, tid):
    token = db.get_integration('flyer')['api_key']
    if not token: return False
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post("https://api.flyerhubs.com/check_task", json={"key": token, "user_id": uid, "signature": tid}, headers={"Content-Type": "application/json"}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("status") == "completed"
        except Exception: pass
    return False

async def get_new_task(uid):
    with db.get_conn() as conn: srv_names = [s['name'] for s in conn.execute("SELECT name FROM integrations WHERE status = 'on' AND role = 'tasks'").fetchall()]
    for srv in ["piarflow", "tgrass", "trafsly", "subgram", "flyer"]:
        if srv in srv_names:
            try:
                t = await (pf_get(uid) if srv == "piarflow" else tg_get(uid) if srv == "tgrass" else tr_get(uid) if srv == "trafsly" else sg_get(uid) if srv == "subgram" else fl_get(uid))
                if t: return t
            except Exception: pass
    return None

async def check_task_status(srv, uid, tid):
    if srv == "piarflow": return await pf_check(uid, tid)
    if srv == "tgrass": return await tg_check(uid, tid)
    if srv == "trafsly": return await tr_check(uid, tid)
    if srv == "subgram": return await sg_check(uid, tid)
    if srv == "flyer": return await fl_check(uid, tid)
    return False

async def get_bh_tasks(uid):
    try: entry_count = int(db.get_setting("botohub_entry_count"))
    except Exception: entry_count = 2
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(BOTOHUB_URL, json={"user_id": uid, "chat_id": uid, "max_sponsors": entry_count}, headers={"Auth": BOTOHUB_TOKEN}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "ok": return None
                    return [{"id": sp.get("id"), "url": sp.get("link")} for sp in d.get("sponsors", [])] or None
        except Exception: pass
    return None

# ================= START & TASKS =================
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
        if ref_id:
            db.create_pending_referral(uid, ref_id)
            uname = "@" + message.from_user.username if message.from_user.username else "Пользователь"
            try: await bot.send_message(ref_id, f'⚡️ <b>{uname}</b> присоединился по твоей ссылке!\n\nТы получишь ⭐, как только он подпишется на спонсоров.')
            except Exception: pass
        if ad_code_val:
            db.track_ad_click(ad_code_val); db.set_user_ad_code(uid, ad_code_val)
    else: db.update_username(uid, message.from_user.username)

    if promo_code:
        ok, msg = db.activate_promo(promo_code, uid)
        if ok: await message.answer(msg)

    if db.get_setting("priv_enabled") == "1":
        ptxt, pmedia, p_btns_json = db.get_setting("priv_text"), db.get_setting("priv_media"), db.get_setting("priv_buttons")
        p_kb = kb.build_kb_from_rows(json.loads(p_btns_json)) if p_btns_json and p_btns_json != "[]" else None
        if pmedia:
            if pmedia.startswith("photo:"): await message.answer_photo(photo=pmedia.replace("photo:", ""), caption=ptxt, reply_markup=p_kb)
            elif pmedia.startswith("video:"): await message.answer_video(video=pmedia.replace("video:", ""), caption=ptxt, reply_markup=p_kb)
            else: await message.answer(ptxt, reply_markup=p_kb)
        else: await message.answer(ptxt, reply_markup=p_kb)
        await asyncio.sleep(3)

    if db.get_setting("botohub_enabled") == "1":
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
        u = db.get_user(uid)
        uname = "@" + u['username'] if u['username'] else "Пользователь"
        try: await bot.send_message(ref, f'⭐ Твой реферал <b>{uname}</b> подписался на спонсоров: <b>+{fmt(bns)} ⭐</b>')
        except Exception: pass
    await send_main_menu(message)

@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery):
    if db.get_setting("botohub_enabled") != "1": return await finish_start(call.message, call.from_user.id)
    op_tasks = await get_bh_tasks(call.from_user.id)
    if not op_tasks:
        try: await call.message.delete()
        except Exception: pass
        await finish_start(call.message, call.from_user.id)
        await call.answer()
    else: await call.answer("Вы подписались не на все каналы!", show_alert=True)

async def send_main_menu(message: Message):
    t = safe_format(db.get_setting("menu_text"), ref_bonus=db.get_setting("ref_bonus"))
    await send_av(message, t, kb.main_menu_kb())

@dp.callback_query(F.data == "menu_back")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except Exception: pass
    await send_main_menu(call.message)
    await call.answer()

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
            if not new_t: return await message.answer("😔 На данный момент нет доступных заданий.", reply_markup=kb.back_kb())
            if not new_t.get("link") or not str(new_t["link"]).startswith("http"): return await message.answer("😔 Ошибка на стороне сервиса заданий.", reply_markup=kb.back_kb())
            db.save_task(uid, new_t["srv"], new_t["tid"], new_t["link"])
            task = db.get_pending_task(uid)
        await message.answer(safe_format(db.get_setting("task_text"), reward=db.get_setting("task_reward")), reply_markup=kb.task_kb(task["link"]))
    except Exception as e: await message.answer("😔 Произошла ошибка при загрузке задания.", reply_markup=kb.back_kb())

@dp.callback_query(F.data == "check_task")
async def check_task_cb(call: CallbackQuery):
    uid = call.from_user.id
    task = db.get_pending_task(uid)
    if not task: return await call.answer("Задание не найдено.", show_alert=True)
    try: await call.message.edit_text("⏳ Проверяем...")
    except Exception: pass
    
    is_done = await check_task_status(task['service'], uid, task['task_id'])
    if not is_done and task['service'] == 'tgrass':
        await asyncio.sleep(2.5)
        is_done = await check_task_status(task['service'], uid, task['task_id'])

    if is_done:
        reward = float(db.get_setting("task_reward"))
        db.add_balance(uid, reward)
        db.mark_task_completed(uid, task['service'], task['task_id'], reward)
        db.mark_task_status(task['id'], 'done')
        try: await call.message.edit_text(f"✅ Выполнено! Начислено: {fmt(reward)} ⭐")
        except Exception: pass
        await asyncio.sleep(1.5)
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
    await call.answer("Пропущено", show_alert=True)
    try: await call.message.delete()
    except Exception: pass
    await send_next_task(call.message, call.from_user.id)

# ================= PROFILE, REFS, STATS, WITHDRAW =================
@dp.callback_query(F.data == "menu_profile")
async def menu_profile(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    u = db.get_user(call.from_user.id)
    uname = "@" + u['username'] if u['username'] else "Юзер"
    t = safe_format(db.get_setting("profile_text"), username=uname, total_refs=db.get_pending_refs_count(u['user_id']) + db.get_confirmed_refs_count(u['user_id']), total_earned=fmt(u['total_earned']), balance=fmt(u['balance']), user_id=u['user_id'], tasks_completed=u['tasks_completed'])
    await send_av(call.message, t, kb.back_kb())

@dp.callback_query(F.data == "menu_refs")
async def menu_refs(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    uid = call.from_user.id
    u = db.get_user(uid)
    link = f"https://t.me/{(await bot.get_me()).username}?start={uid}"
    refs = db.get_user_referrals(uid)
    txt_refs = "".join([f"├ @{r['username'] if r['username'] else 'id'+str(r['user_id'])} — {'Ожидает' if r['status']=='pending' else '✅'}\n" for r in refs]) or "├ Пока никого нет\n"
    t = safe_format(db.get_setting("ref_text"), ref_bonus=db.get_setting("ref_bonus"), ref_link=link, total_refs=db.get_pending_refs_count(uid) + db.get_confirmed_refs_count(uid), confirmed_refs=db.get_confirmed_refs_count(uid), ref_list=txt_refs, balance=fmt(u['balance']))
    await send_av(call.message, t, kb.back_kb())

@dp.callback_query(F.data == "menu_instruction")
async def menu_instruction(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    await send_av(call.message, db.get_setting("instruction_text"), kb.back_kb())

@dp.callback_query(F.data == "menu_stats")
async def menu_stats(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    s = db.get_stats()
    await send_av(call.message, safe_format(db.get_setting("stats_text"), total_users=s['total'], total_withdrawn=fmt(s['total_stars'])), kb.stats_kb())

@dp.callback_query(F.data == "top_balance")
async def top_balance(call: CallbackQuery):
    users = db.get_top_balance()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по балансу</b>\n\n" + "".join([f"{i}. @{u['username'] if u['username'] else 'id'+str(u['user_id'])} — <b>{fmt(u['balance'])}</b> ⭐\n" for i, u in enumerate(users, 1)])
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

@dp.callback_query(F.data == "top_refs")
async def top_refs(call: CallbackQuery):
    users = db.get_top_refs()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по рефералам</b>\n\n" + "".join([f"{i}. @{u['username'] if u['username'] else 'id'+str(u['user_id'])} — <b>{u['refs']}</b> чел.\n" for i, u in enumerate(users, 1)])
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

@dp.callback_query(F.data == "top_earn")
async def top_earn(call: CallbackQuery):
    with db.get_conn() as conn: users = conn.execute("SELECT user_id, username, total_earned FROM users ORDER BY total_earned DESC LIMIT 10").fetchall()
    if not users: return await call.answer("🏆 В топе пока никого нет!", show_alert=True)
    txt = "🏆 <b>Топ по заработку</b>\n\n" + "".join([f"{i}. @{u['username'] if u['username'] else 'id'+str(u['user_id'])} — <b>{fmt(u['total_earned'])}</b> ⭐\n" for i, u in enumerate(users, 1)])
    await call.message.edit_text(txt, reply_markup=kb.back_kb("menu_stats"))

@dp.callback_query(F.data == "menu_withdraw")
async def menu_withdraw(call: CallbackQuery, state: FSMContext):
    try: await call.message.delete()
    except Exception: pass
    u = db.get_user(call.from_user.id)
    req = int(db.get_setting("withdraw_friends_required"))
    conf = db.get_confirmed_refs_count(u['user_id'])
    t = safe_format(db.get_setting("withdraw_text"), balance=fmt(u['balance']), amounts=", ".join(map(str, WITHDRAW_AMOUNTS)))
    if conf < req: t += f"\n\n⚠️ <b>Внимание!</b> Для вывода нужно пригласить минимум <b>{req}</b> друзей (у тебя {conf})."
    await send_av(call.message, t, kb.withdraw_kb())
    await state.set_state(UserStates.w_amount)

async def do_withdraw(message: Message, amount: float):
    u = db.get_user(message.from_user.id)
    if round(u['balance'], 2) < amount: return await message.answer(f"❌ Не хватает звёзд. Баланс: {fmt(u['balance'])} ⭐")
    req, conf = int(db.get_setting("withdraw_friends_required")), db.get_confirmed_refs_count(u['user_id'])
    if conf < req: return await message.answer(f"❌ Нужно пригласить друзей: {req} (у вас {conf})")
    wid = db.create_withdrawal(u['user_id'], amount)
    await message.answer(f'✅ Заявка <b>#{wid}</b> на <b>{fmt(amount)}</b> ⭐ создана.\n\nСрок вывода: 5 минут — 24 часа.', reply_markup=kb.back_kb())
    
    with db.get_conn() as conn: refs = conn.execute("SELECT user_id, username FROM users WHERE referrer_id = ? AND passed_op = 1", (u['user_id'],)).fetchall()
    refs_str = "".join([f"├ @{r['username'] if r['username'] else 'id'+str(r['user_id'])}\n" for r in refs]) or "├ Нет друзей\n"
    admin_msg = f"💸 <b>Новая заявка на вывод #{wid}</b>\n\n👤 Пользователь: @{u['username'] or 'нет'} (<code>{u['user_id']}</code>)\n💰 Сумма: <b>{fmt(amount)}</b> ⭐\n👥 Рефералов: {conf}\n🎯 Заданий: {u['tasks_completed']}\n✅ Прошел ОП: {'✅ Да' if u['passed_op'] else '❌ Нет'}\n💵 Остаток: {fmt(u['balance'] - amount)} ⭐\n\n📊 <b>Кого он привел:</b>\n{refs_str}"
    try: await bot.send_message(ADMIN_ID, admin_msg, reply_markup=kb.back_admin_kb())
    except Exception: pass

@dp.message(UserStates.w_amount)
async def process_wd_text(message: Message, state: FSMContext):
    try: amount = float(message.text.strip().replace(',', '.'))
    except ValueError: return await message.answer("❌ Введи число (например: 15, 25, 50, 100) или нажми кнопку.")
    if amount not in WITHDRAW_AMOUNTS: return await message.answer(f"❌ Неверная сумма. Доступно: {', '.join(map(str, WITHDRAW_AMOUNTS))}")
    await state.clear()
    await do_withdraw(message, amount)

@dp.callback_query(F.data.regexp(r"^wd_\d+$"))
async def process_wd_btn(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except Exception: pass
    await do_withdraw(call.message, float(call.data.split("_")[1]))
    await call.answer()
    # ================= АДМИН\КА: БАЗАn И СТАТИСТИКА =================З
@dp.message(Command("admin"), IsAdminFilter())
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())

@dp.callback_query(F.data == "admin_back", StateFilter("*"), IsAdminFilter())
async def admin_back_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_kb())
    except Exception as e:
        if "message is not modified" not in str(e): print(f"Ошибка в админке: {e}")
    await call.answer()

@dp.callback_query(F.data == "admin_noop", IsAdminFilter())
async def admin_noop(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data == "stats", IsAdminFilter())
async def admin_detailed_stats(c: CallbackQuery):
    s = db.get_stats()
    txt = "📊 <b>МЕГА-СТАТИСТИКА БОТА</b>\n\n"
    txt += "👥 <b>Пользователи:</b>\n"
    txt += "├ Всего: <b>" + str(s['total']) + "</b>\n"
    txt += "├ За сегодня: <b>" + str(s['today']) + "</b>\n"
    txt += "└ Активных сегодня: <b>" + str(s['active_today']) + "</b>\n\n"
    txt += "💰 <b>Экономика:</b>\n"
    txt += "├ Заработано юзерами: <b>" + fmt(s['total_earned']) + "</b> ⭐\n"
    txt += "├ Общий баланс: <b>" + fmt(s['total_balance']) + "</b> ⭐\n"
    txt += "└ Заданий выполнено: <b>" + str(s['tasks']) + "</b>\n\n"
    txt += "💸 <b>Выводы:</b>\n"
    txt += "├ Ожидают: <b>" + str(s['pending']) + "</b> (на " + fmt(s['pending_stars']) + " ⭐)\n"
    txt += "└ Выплачено: <b>" + str(s['done']) + "</b> (на " + fmt(s['total_stars']) + " ⭐)"
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())
    await c.answer()

# ================= АДМИНКА: ЗАЯВКИ НА ВЫВОД =================
@dp.callback_query(F.data == "wd_list", IsAdminFilter())
async def admin_wd_list(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    if not wds: return await call.message.edit_text("Нет активных заявок.", reply_markup=kb.wd_empty_kb())
    await show_wd_page(call, 0)

async def show_wd_page(call: CallbackQuery, idx: int):
    wds = db.get_pending_withdrawals()
    if not wds: return await call.message.edit_text("Заявок больше нет.", reply_markup=kb.wd_empty_kb())
    idx = max(0, min(idx, len(wds) - 1))
    w = wds[idx]
    u = db.get_user(w['user_id'])

    with db.get_conn() as conn: refs_list = conn.execute("SELECT user_id, username FROM users WHERE referrer_id = ? AND passed_op = 1", (u['user_id'],)).fetchall()

    refs_str = ""
    for r in refs_list[:5]:
        if r['username']: refs_str += "├ @" + r['username'] + "\n"
        else: refs_str += "├ id" + str(r['user_id']) + " (<a href='tg://user?id=" + str(r['user_id']) + "'>написать</a>)\n"
    if len(refs_list) > 5: refs_str += "├ ...\n"
    if not refs_str: refs_str = "├ Нет друзей\n"

    reg_date = u['registered_at'][:10] if u['registered_at'] else "—"
    uname = "@" + u['username'] if u['username'] else "id" + str(u['user_id'])
    
    txt = "💸 <b>Заявка #" + str(w['id']) + "</b>\n\n"
    txt += "👤 Юзер: " + uname + " (<code>" + str(u['user_id']) + "</code>)\n"
    txt += "💰 Сумма: <b>" + fmt(w['amount']) + "</b> ⭐\n"
    txt += "📅 Регистрация: " + reg_date + "\n\n"
    txt += "📊 <b>Аналитика (друзья):</b>\n" + refs_str
    txt += "└ Заданий: " + str(u['tasks_completed']) + " | Заработал: " + fmt(u['total_earned']) + " ⭐"
    await call.message.edit_text(txt, reply_markup=kb.wd_page_kb(w['id'], idx, len(wds)))

@dp.callback_query(F.data.startswith("wd_page:"), IsAdminFilter())
async def wd_page_nav(call: CallbackQuery):
    await show_wd_page(call, int(call.data.split(":")[1]))

@dp.callback_query(F.data == "wd_noop", IsAdminFilter())
async def wd_noop(call: CallbackQuery):
    await call.answer()

@dp.callback_query(F.data.startswith("wd_ok:"), IsAdminFilter())
async def wd_ok(call: CallbackQuery):
    wid = int(call.data.split(":")[1])
    db.set_withdrawal_status(wid, 'completed')
    w = db.get_withdrawal(wid)
    if w:
        msg = '✅ Заявка <b>#' + str(wid) + '</b> на <b>' + fmt(w["amount"]) + ' ⭐</b> выплачена!'
        try: await bot.send_message(w['user_id'], msg)
        except Exception: pass
    await call.answer("Одобрено!")
    await show_wd_page(call, 0)

@dp.callback_query(F.data.startswith("wd_no:"), IsAdminFilter())
async def wd_no(call: CallbackQuery):
    wid = int(call.data.split(":")[1])
    db.set_withdrawal_status(wid, 'rejected')
    w = db.get_withdrawal(wid)
    if w:
        db.add_balance(w['user_id'], w['amount'])
        try: await bot.send_message(w['user_id'], "❌ Заявка на вывод отклонена. Средства возвращены на баланс.")
        except Exception: pass
    await call.answer("Отклонено")
    await show_wd_page(call, 0)

@dp.callback_query(F.data == "wd_accept_all", IsAdminFilter())
async def wd_accept_all(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    for w in wds:
        db.set_withdrawal_status(w['id'], 'completed')
        msg = '✅ Заявка <b>#' + str(w["id"]) + '</b> на <b>' + fmt(w["amount"]) + ' ⭐</b> выплачена!'
        try: await bot.send_message(w['user_id'], msg)
        except Exception: pass
    await call.message.edit_text("✅ Все заявки одобрены.", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "wd_reject_all", IsAdminFilter())
async def wd_reject_all(call: CallbackQuery):
    wds = db.get_pending_withdrawals()
    for w in wds:
        db.set_withdrawal_status(w['id'], 'rejected')
        db.add_balance(w['user_id'], w['amount'])
        try: await bot.send_message(w['user_id'], "❌ Заявка отклонена. Средства возвращены.")
        except Exception: pass
    await call.message.edit_text("❌ Все заявки отклонены.", reply_markup=kb.back_admin_kb())

# ================= АДМИНКА: ЮЗЕРЫ =================
@dp.callback_query(F.data == "user_find", IsAdminFilter())
async def admin_fu(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введи ID или @username:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_search)

@dp.message(AdminStates.w_u_search, IsAdminFilter())
async def search_user(message: Message, state: FSMContext):
    q = message.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await message.answer("❌ Не найден.")

    with db.get_conn() as conn: refs_list = conn.execute("SELECT user_id, username FROM users WHERE referrer_id = ? AND passed_op = 1", (u['user_id'],)).fetchall()
    
    refs_str = ""
    for r in refs_list[:5]:
        if r['username']: refs_str += "├ @" + r['username'] + "\n"
        else: refs_str += "├ id" + str(r['user_id']) + " (<a href='tg://user?id=" + str(r['user_id']) + "'>написать</a>)\n"
    if len(refs_list) > 5: refs_str += "├ ...\n"
    if not refs_str: refs_str = "├ Нет друзей\n"

    reg = u['registered_at'][:10] if u['registered_at'] else "—"
    uname = "@" + u['username'] if u['username'] else "—"
    
    t = "👤 <b>Профиль</b>\nID: <code>" + str(u['user_id']) + "</code>\nНик: " + uname + "\nРега: " + reg + "\n"
    t += "Баланс: <b>" + fmt(u['balance']) + "</b> ⭐\nЗаработал: <b>" + fmt(u['total_earned']) + "</b>\n"
    t += "Заданий: <b>" + str(u['tasks_completed']) + "</b>\n\n<b>Друзья:</b>\n" + refs_str
    t += "\nБан: " + ('Да' if u['is_banned'] else 'Нет')
    await message.answer(t, reply_markup=kb.user_action_kb(u['user_id'], u['is_banned']))
    await state.clear()

@dp.callback_query(F.data.startswith("u_ban:"), IsAdminFilter())
async def user_ban(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    u = db.get_user(uid)
    new_status = 0 if u['is_banned'] else 1
    db.toggle_ban(uid, new_status)
    await call.answer("Статус обновлен")
    
    u2 = db.get_user(uid)
    reg = u2['registered_at'][:10] if u2['registered_at'] else "—"
    uname = "@" + u2['username'] if u2['username'] else "—"
    t = "👤 <b>Профиль</b>\nID: <code>" + str(u2['user_id']) + "</code>\nНик: " + uname + "\nРега: " + reg + "\n"
    t += "Баланс: <b>" + fmt(u2['balance']) + "</b>аработал: <b>" + fmt(u2['total_earned']) + "</b>\n"
    t += "Заданий: <b>" + str(u2['tasks_completed']) + "</b>\n\nБан: " + ('Да' if u2['is_banned'] else 'Нет')
    try: await call.message.edit_text(t, reply_markup=kb.user_action_kb(uid, u2['is_banned']))
    except Exception: pass

@dp.callback_query(F.data.startswith("u_bal:"), IsAdminFilter())
async def user_bal(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split(":")[1])
    await state.update_data(bal_uid=uid, give_mode=False)
    await call.message.edit_text("Введи сумму (например 50 или -20):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)

@dp.callback_query(F.data == "give_start", IsAdminFilter())
async def give_start(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи ID юзера для начисления:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)
    await state.update_data(bal_uid=None, give_mode=True)

@dp.message(AdminStates.w_u_bal, IsAdminFilter())
async def save_bal_or_give(message: Message, state: FSMContext):
    d = await state.get_data()
    if d.get('give_mode') and d.get('bal_uid') is None:
        try:
            uid = int(message.text.strip())
            u = db.get_user(uid)
            if not u: return await message.answer("❌ Юзер не найден.")
            await state.update_data(bal_uid=uid)
            await message.answer("Юзер: " + str(u['username'] or 'id'+str(uid)) + "\nВведи сумму начисления:")
        except Exception: await message.answer("Ошибка. Введи числовой ID.")
    else:
        try:
            a = float(message.text)
            db.add_balance(d['bal_uid'], a)
            await message.answer("✅ Баланс изменен!", reply_markup=kb.back_admin_kb())
            await state.clear()
        except Exception: await message.answer("Ошибка. Введи число.")

# ================= АДМИНКА: ПРОМОКОДЫ =================
@dp.callback_query(F.data == "promos", IsAdminFilter())
async def admin_promos(c: CallbackQuery):
    await c.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=kb.promos_kb())
    await c.answer()

@dp.callback_query(F.data == "promo_list", IsAdminFilter())
async def promo_list(c: CallbackQuery):
    promos = db.get_all_promos()
    if not promos: return await c.message.edit_text("Нет промокодов.", reply_markup=kb.back_admin_kb())
    txt = "📜 <b>Список промокодов:</b>\n\n"
    for p in promos: txt += "<code>" + p['code'] + "</code> | " + str(p['amount']) + " ⭐ | " + str(p['used']) + "/" + str(p['max_uses']) + "\n"
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "promo_create", IsAdminFilter())
async def promo_create(c: CallbackQuery, state: FSMContext):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Обычный (просто звезды)", callback_data="p_type:0"))
    b.row(InlineKeyboardButton(text="С ОП (задания)", callback_data="p_type:1"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="promos"))
    await c.message.edit_text("Выбери тип промокода:", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("p_type:"), IsAdminFilter())
async def promo_type(c: CallbackQuery, state: FSMContext):
    await state.update_data(is_op=int(c.data.split(":")[1]))
    await c.message.edit_text("Введи сумму чека (звезды):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_p_sum)

@dp.message(AdminStates.w_p_sum, IsAdminFilter())
async def promo_sum(m: Message, state: FSMContext):
    try:
        await state.update_data(p_amount=float(m.text))
        await m.answer("Сколько активаций (лимит)?")
        await state.set_state(AdminStates.w_p_act)
    except Exception: await m.answer("Ошибка. Введи число.")

@dp.message(AdminStates.w_p_act, IsAdminFilter())
async def promo_act(m: Message, state: FSMContext):
    try:
        await state.update_data(p_uses=int(m.text))
        d = await state.get_data()
        if d['is_op']:
            await state.update_data(selected_services=[])
            await m.answer("Выбери сервисы для ОП:", reply_markup=kb.promo_srv_kb([]))
            await state.set_state(AdminStates.w_p_srv)
        else:
            code = "promo_" + str(random.randint(100000, 999999))
            db.create_promo(code, d['p_amount'], d['p_uses'], is_op=0)
            me = await bot.get_me()
            await m.answer("✅ Чек создан!\nСсылка: https://t.me/" + me.username + "?start=" + code, reply_markup=kb.back_admin_kb())
            await state.clear()
    except Exception: await m.answer("Ошибка. Введи число.")

@dp.callback_query(F.data.startswith("psrv:"), AdminStates.w_p_srv, IsAdminFilter())
async def promo_srv_toggle(call: CallbackQuery, state: FSMContext):
    srv = call.data.split(":")[1]
    d = await state.get_data()
    services = d.get('selected_services', [])
    if srv in services: services.remove(srv)
    else: services.append(srv)
    await state.update_data(selected_services=services)
    await call.message.edit_reply_markup(reply_markup=kb.promo_srv_kb(services))
    await call.answer()

@dp.callback_query(F.data == "psrv_done", AdminStates.w_p_srv, IsAdminFilter())
async def promo_srv_done(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if not d.get('selected_services'): return await call.answer("Выбери хотя бы один сервис!", show_alert=True)
    await call.message.edit_text("Сколько спонсоров пройти? (введи число)")
    await state.set_state(AdminStates.w_p_cnt)

@dp.message(AdminStates.w_p_cnt, IsAdminFilter())
async def promo_cnt(m: Message, state: FSMContext):
    try:
        d = await state.get_data()
        cnt = int(m.text)
        srv_str = ",".join(d['selected_services'])
        code = "promo_op_" + str(random.randint(100000, 999999))
        db.create_promo(code, d['p_amount'], d['p_uses'], is_op=1, op_service=srv_str, op_count=cnt)
        me = await bot.get_me()
        await m.answer("✅ Чек с ОП создан!\nСервисы: " + srv_str + "\nСсылка: https://t.me/" + me.username + "?start=" + code, reply_markup=kb.back_admin_kb())
        await state.clear()
    except Exception: await m.answer("Ошибка. Введи число.")

# ================= АДМИНКА: РЕКЛАМА (МЕТКИ) =================
@dp.callback_query(F.data == "ad_menu", IsAdminFilter())
async def admin_ads(c: CallbackQuery):
    await c.message.edit_text("📊 <b>Реклама (метки)</b>", reply_markup=kb.ad_menu_kb())
    await c.answer()

@dp.callback_query(F.data == "ad_list", IsAdminFilter())
async def ad_list(c: CallbackQuery):
    ads = db.get_all_ads()
    if not ads: return await c.message.edit_text("Нет меток.", reply_markup=kb.back_admin_kb())
    txt = "📜 <b>Список меток:</b>\n\n"
    for a in ads: txt += "<code>" + a['code'] + "</code> | Кликов: " + str(a['clicks']) + " | Цена: " + str(a['price']) + "₽\nСтата: <code>/stat_" + a['code'] + "</code>\n\n"
    await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "ad_add", IsAdminFilter())
async def ad_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи код метки (например tiktok):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_ad_code)

@dp.message(AdminStates.w_ad_code, IsAdminFilter())
async def ad_code(m: Message, state: FSMContext):
    await state.update_data(ad_code=m.text.lower())
    await m.answer("Введи ID или @username рекламодателя:")
    await state.set_state(AdminStates.w_ad_own)

@dp.message(AdminStates.w_ad_own, IsAdminFilter())
async def ad_own(m: Message, state: FSMContext):
    q = m.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await m.answer("Не найден.")
    await state.update_data(ad_own=u['user_id'])
    await m.answer("Введи цену за переход (в рублях):")
    await state.set_state(AdminStates.w_ad_prc)

@dp.message(AdminStates.w_ad_prc, IsAdminFilter())
async def ad_prc(m: Message, state: FSMContext):
    try:
        d = await state.get_data()
        prc = float(m.text)
        db.add_ad_source(d['ad_code'], d['ad_own'], prc)
        me = await bot.get_me()
        await m.answer("✅ Метка создана!\nСсылка: https://t.me/" + me.username + "?start=ad_" + d['ad_code'] + "\nСтата: /stat_" + d['ad_code'], reply_markup=kb.back_admin_kb())
        await state.clear()
    except Exception: await m.answer("Ошибка. Введи число.")

@dp.message(F.text.startswith("/stat_"), IsAdminFilter())
async def ad_stat_cmd(m: Message):
    code = m.text.split("_", 1)[1].lower()
    text, b = await _build_ad_stat(code)
    if not text: return await m.answer("❌ Метка не найдена.")
    await m.answer(text, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("upd_stat:"), IsAdminFilter())
async def upd_stat(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    text, b = await _build_ad_stat(code)
    if not text: return await c.answer("Не найдено", show_alert=True)
    await c.message.edit_text(text, reply_markup=b.as_markup())
    await c.answer("Обновлено")

async def _build_ad_stat(code: str):
    src = db.get_ad_source(code)
    if not src: return None, None
    with db.get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ?", (code,)).fetchone()[0]
        passed_op = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ? AND passed_op = 1", (code,)).fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM task_completed tc JOIN users u ON tc.user_id = u.user_id WHERE u.ad_code = ?", (code,)).fetchone()[0]
        earned = conn.execute("SELECT SUM(balance) FROM users WHERE ad_code = ?", (code,)).fetchone()[0] or 0.0
        withdrawn = conn.execute("SELECT SUM(amount) FROM withdrawals w JOIN users u ON w.user_id = u.user_id WHERE u.ad_code = ? AND w.status = 'completed'", (code,)).fetchone()[0] or 0.0
    
    text = "📊 <b>Статистика метки: " + code + "</b>\n\n👤 Переходов: <b>" + str(src['clicks']) + "</b>\n🆕 Зарегалось: <b>" + str(total_users) + "</b>\n✅ Прошли ОП: <b>" + str(passed_op) + "</b>\n🎯 Заданий: <b>" + str(tasks) + "</b>\n💰 Заработали: <b>" + fmt(earned) + "</b> ⭐\n💸 Вывели: <b>" + fmt(withdrawn) + "</b> ⭐\n\n💵 Цена: <b>" + str(src['price']) + " ₽</b>\n👤 Рекла: <code>" + str(src['owner_id']) + "</code>"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="upd_stat:" + code))
    return text, b

# ================= АДМИНКА: АДМИНЫ =================
@dp.callback_query(F.data == "admins_menu", IsAdminFilter())
async def admins_menu(c: CallbackQuery):
    admins = db.get_admins()
    txt = "👑 <b>Админы бота</b>\n\nГлавный админ (из .env): <code>" + str(ADMIN_ID) + "</code>\nЕго нельзя удалить.\n\nНажми на 🗑 у админа, чтобы удалить его.\n\n📋 <b>Список:</b>\n"
    for a in admins:
        crown = "👑" if a["is_main"] else "•"
        name = "@" + a['username'] if a['username'] else "без_юзернейма"
        txt += crown + " " + name + " (<code>" + str(a['user_id']) + "</code>)\n"
    await c.message.edit_text(txt, reply_markup=kb.admins_list_kb(admins))
    await c.answer()

@dp.callback_query(F.data == "admin_add", IsAdminFilter())
async def admin_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи ID или @username нового админа:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_admin_add)

@dp.message(AdminStates.w_admin_add, IsAdminFilter())
async def admin_add_save(m: Message, state: FSMContext):
    q = m.text.strip()
    if q.startswith("@"): q = q[1:]

    if q.isdigit(): uid = int(q)
    else:
        u = db.get_user_by_username(q)
        if not u:
            await state.clear()
            return await m.answer("❌ Пользователь с таким @username не найден в боте.")
        uid = u['user_id']

    if db.is_main_admin(uid):
        await state.clear()
        return await m.answer("👑 Это главный админ, он уже в списке.", reply_markup=kb.back_admin_kb())

    if db.is_admin(uid):
        await state.clear()
        return await m.answer("⚠️ Этот пользователь уже админ.", reply_markup=kb.back_admin_kb())

    ok = db.add_admin(uid, m.from_user.id)
    await state.clear()
    if ok: await m.answer("✅ Админ <code>" + str(uid) + "</code> добавлен!", reply_markup=kb.back_admin_kb())
    else: await m.answer("⚠️ Не удалось добавить.", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data.startswith("admin_del:"), IsAdminFilter())
async def admin_del_confirm(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    if db.is_main_admin(uid): return await c.answer("Главного админа удалить нельзя", show_alert=True)
    u = db.get_user(uid)
    name = "@" + u['username'] if (u and u['username']) else str(uid)
    await c.message.edit_text("Удалить админа <b>" + name + "</b> (<code>" + str(uid) + "</code>)?", reply_markup=kb.admin_confirm_delete_kb(uid))
    await c.answer()

@dp.callback_query(F.data.startswith("admin_del_ok:"), IsAdminFilter())
async def admin_del_do(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    db.remove_admin(uid)
    await admins_menu(c)
    # ================= ПАРСЕР МАССОВЫХ КНОПОК =================
def parse_bulk_buttons(text: str):
    color_map = {'с': 'primary', 'синяя': 'primary', 'з': 'success', 'зеленая': 'success', 'зелёная': 'success', 'к': 'danger', 'красная': 'danger', 'о': 'None', 'обычная': 'None', 'none': 'None'}
    rows = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line: continue
        buttons_in_line = []
        parts = re.split(r'\s*&&\s*', line)
        for part in parts:
            part = part.strip()
            if not part: continue
            match = re.match(r'^(.+)\s+-\s+(https?://\S+|action:\S+)\s+-\s+(\S+)$', part)
            if not match: return None, "Неверный формат: <code>" + part + "</code>\n\nФормат: <code>ТЕКСТ - ССЫЛКА - ЦВЕТ</code>"
            btn_text, btn_url, color_raw = match.group(1).strip(), match.group(2).strip(), match.group(3).strip().lower()
            color = color_map.get(color_raw)
            if color is None: return None, "Неизвестный цвет: <code>" + color_raw + "</code>\n\nЦвета: <b>с</b> / <b>з</b> / <b>к</b> / <b>о</b>"
            if len(btn_text) > 64: return None, "Текст кнопки слишком длинный (макс 64): <code>" + btn_text[:30] + "...</code>"
            buttons_in_line.append({"text": btn_text, "url": btn_url, "color": color})
        if buttons_in_line: rows.append(buttons_in_line)
    if not rows: return None, "Пустой ввод. Отправь хотя бы одну кнопку."
    return rows, None

def normalize_button_rows(data):
    if not data: return []
    try: parsed = json.loads(data) if isinstance(data, str) else data
    except Exception: return []
    if not parsed: return []
    if isinstance(parsed[0], dict): return [[btn] for btn in parsed]
    return parsed

# ================= АДМИНКА: ПРИВАТКА =================
@dp.callback_query(F.data == "priv_menu", IsAdminFilter())
async def admin_priv(c: CallbackQuery):
    status = "🟢 Включена" if db.get_setting("priv_enabled") == "1" else "🔴 Выключена"
    media = db.get_setting("priv_media") or "Нет"
    rows = normalize_button_rows(db.get_setting("priv_buttons") or "[]")
    total_btns = sum(len(r) for r in rows)

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 Выкл" if db.get_setting("priv_enabled") == "1" else "🟢 Вкл", callback_data="priv_toggle"))
    b.row(InlineKeyboardButton(text="✏️ Текст", callback_data="priv_edit_text"))
    b.row(InlineKeyboardButton(text="🖼 Медиа", callback_data="priv_edit_media"))
    b.row(InlineKeyboardButton(text="🔗 Кнопки (" + str(total_btns) + ")", callback_data="priv_menu_btns"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("🎛 <b>Приватка</b>\n\nСтатус: " + status + "\nМедиа: " + ('Есть' if media != 'Нет' else 'Нет') + "\nКнопок: " + str(total_btns), reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data == "priv_toggle", IsAdminFilter())
async def priv_toggle(c: CallbackQuery):
    cur = db.get_setting("priv_enabled")
    db.set_setting("priv_enabled", "0" if cur == "1" else "1")
    await admin_priv(c)

@dp.callback_query(F.data == "priv_edit_text", IsAdminFilter())
async def priv_edit(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь новый текст приватки (HTML и прем-эмодзи):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await state.update_data(set_key="priv_text", is_media=False)

@dp.callback_query(F.data == "priv_edit_media", IsAdminFilter())
async def priv_edit_media(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь фото или видео для приватки:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await state.update_data(set_key="priv_media", is_media=True)

@dp.callback_query(F.data == "priv_menu_btns", IsAdminFilter())
async def priv_menu_btns(c: CallbackQuery):
    rows = normalize_button_rows(db.get_setting("priv_buttons") or "[]")
    total_btns = sum(len(r) for r in rows)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Добавить кнопки", callback_data="priv_add_btn", style="success"))
    if rows: b.row(InlineKeyboardButton(text="🗑 Очистить все", callback_data="priv_clear_btns", style="danger"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="priv_menu"))

    txt = "🔗 <b>Кнопки приватки</b> (всего: " + str(total_btns) + ")\n\n"
    if not rows: txt += "Пока нет кнопок.\n\n"
    else:
        for i, row in enumerate(rows, 1):
            line = " | ".join([btn['text'] + " [" + str(btn.get('color', 'None')) + "]" for btn in row])
            txt += "Ряд " + str(i) + ": " + line + "\n"
        txt += "\n"
    txt += "<b>Формат ввода:</b>\n<code>Текст - https://url - с</code>\n<code>Текст2 - action:menu_earn - з && Текст3 - https://url3 - к</code>\n\n<b>&&</b> = кнопки в одном ряду, <b>энтер</b> = новый ряд.\n\nЦвета: <b>с</b> (синяя), <b>з</b> (зелёная), <b>к</b> (красная), <b>о</b> (обычная)"
    await c.message.edit_text(txt, reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data == "priv_clear_btns", IsAdminFilter())
async def priv_clear_btns(c: CallbackQuery):
    db.set_setting("priv_buttons", "[]")
    await priv_menu_btns(c)

@dp.callback_query(F.data == "priv_add_btn", IsAdminFilter())
async def priv_add_btn(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь кнопки в формате:\n\n<code>Текст - https://url - с</code>\n<code>Текст2 - action:menu_earn - з && Текст3 - https://url3 - к</code>\n\n<b>&&</b> = в ряд, <b>энтер</b> = новый ряд.\n\nЦвета: <b>с</b>, <b>з</b>, <b>к</b>, <b>о</b>", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_priv_btn_bulk)

@dp.message(AdminStates.w_priv_btn_bulk, IsAdminFilter())
async def priv_btn_bulk_save(m: Message, state: FSMContext):
    rows, err = parse_bulk_buttons(m.text)
    if err: return await m.answer("❌ " + err)
    existing = normalize_button_rows(db.get_setting("priv_buttons") or "[]")
    existing.extend(rows)
    db.set_setting("priv_buttons", json.dumps(existing, ensure_ascii=False))
    await state.clear()
    await m.answer("✅ Добавлено " + str(len(rows)) + " ряд(ов) кнопок!", reply_markup=kb.back_admin_kb())

# ================= АДМИНКА: РАССЫЛКА =================
BC_STATE = {"text": "", "media": None, "media_type": None, "limit": 0, "buttons": []}

@dp.callback_query(F.data == "broadcast_menu", IsAdminFilter())
async def bc_menu(c: CallbackQuery):
    total_btns = sum(len(r) for r in BC_STATE.get('buttons', []))
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Текст", callback_data="bc_edit_text"))
    b.row(InlineKeyboardButton(text="📎 Медиа", callback_data="bc_edit_media"))
    b.row(InlineKeyboardButton(text="🔗 Кнопки (" + str(total_btns) + ")", callback_data="bc_edit_btns"))
    b.row(InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bc_preview"))
    b.row(InlineKeyboardButton(text="✅ Отправить", callback_data="bc_start", style="success"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("📢 <b>Умная рассылка</b>\n\nТекст: " + ('✅' if BC_STATE.get('text') else '❌') + "\nМедиа: " + ('✅' if BC_STATE.get('media') else '❌') + "\nКнопок: " + str(total_btns), reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data == "bc_edit_text", IsAdminFilter())
async def bc_edit_text(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь текст (HTML и прем-эмодзи):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_text)

@dp.message(AdminStates.w_bc_text, IsAdminFilter())
async def bc_save_text(m: Message, state: FSMContext):
    BC_STATE['text'] = m.html_text
    await state.clear()
    await m.answer("✅ Текст сохранен!", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "bc_edit_media", IsAdminFilter())
async def bc_edit_media(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь фото или видео:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_media)

@dp.message(AdminStates.w_bc_media, IsAdminFilter())
async def bc_save_media(m: Message, state: FSMContext):
    if m.photo: BC_STATE['media'] = m.photo[-1].file_id; BC_STATE['media_type'] = 'photo'
    elif m.video: BC_STATE['media'] = m.video.file_id; BC_STATE['media_type'] = 'video'
    else: return await m.answer("Нужно фото или видео.")
    await state.clear()
    await m.answer("✅ Медиа сохранено!", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "bc_edit_btns", IsAdminFilter())
async def bc_edit_btns(c: CallbackQuery):
    total_btns = sum(len(r) for r in BC_STATE.get('buttons', []))
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Добавить кнопки", callback_data="bc_add_btn", style="success"))
    if BC_STATE.get('buttons'): b.row(InlineKeyboardButton(text="🗑 Очистить все", callback_data="bc_clear_btns", style="danger"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="broadcast_menu"))

    txt = "🔗 <b>Кнопки рассылки</b> (всего: " + str(total_btns) + ")\n\n"
    if not BC_STATE.get('buttons'): txt += "Пока нет кнопок.\n\n"
    else:
        for i, row in enumerate(BC_STATE['buttons'], 1):
            line = " | ".join([btn['text'] + " [" + str(btn.get('color', 'None')) + "]" for btn in row])
            txt += "Ряд " + str(i) + ": " + line + "\n"
        txt += "\n"
    txt += "<b>Формат ввода:</b>\n<code>Текст - https://url - с</code>\n<code>Текст2 - action:menu_earn - з && Текст3 - https://url3 - к</code>\n\n<b>&&</b> = в ряд, <b>энтер</b> = новый ряд.\n\nЦвета: <b>с</b>, <b>з</b>, <b>к</b>, <b>о</b>"
    await c.message.edit_text(txt, reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data == "bc_clear_btns", IsAdminFilter())
async def bc_clear_btns(c: CallbackQuery):
    BC_STATE['buttons'] = []
    await c.answer("Кнопки очищены!", show_alert=True)
    await bc_edit_btns(c)

@dp.callback_query(F.data == "bc_add_btn", IsAdminFilter())
async def bc_add_btn(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь кнопки в формате:\n\n<code>Текст - https://url - с</code>\n<code>Текст2 - action:menu_earn - з && Текст3 - https://url3 - к</code>\n\n<b>&&</b> = в ряд, <b>энтер</b> = новый ряд.\n\nЦвета: <b>с</b>, <b>з</b>, <b>к</b>, <b>о</b>", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_btn_bulk)

@dp.message(AdminStates.w_bc_btn_bulk, IsAdminFilter())
async def bc_btn_bulk_save(m: Message, state: FSMContext):
    rows, err = parse_bulk_buttons(m.text)
    if err: return await m.answer("❌ " + err)
    if 'buttons' not in BC_STATE: BC_STATE['buttons'] = []
    BC_STATE['buttons'].extend(rows)
    await state.clear()
    await m.answer("✅ Добавлено " + str(len(rows)) + " ряд(ов) кнопок в рассылку!", reply_markup=kb.back_admin_kb())

@dp.callback_query(F.data == "bc_preview", IsAdminFilter())
async def bc_preview(c: CallbackQuery):
    text = BC_STATE.get('text', '')
    media = BC_STATE.get('media')
    mtype = BC_STATE.get('media_type')
    if not text and not media: return await c.answer("Пусто", show_alert=True)
    markup = kb.build_kb_from_rows(BC_STATE.get('buttons', []))
    if media:
        if mtype == 'photo': await c.message.answer_photo(media, caption=text, reply_markup=markup)
        else: await c.message.answer_video(media, caption=text, reply_markup=markup)
    else: await c.message.answer(text, reply_markup=markup)
    await c.answer()

@dp.callback_query(F.data == "bc_start", IsAdminFilter())
async def bc_start(c: CallbackQuery):
    if not BC_STATE.get('text') and not BC_STATE.get('media'): return await c.answer("Сначала задай текст или медиа!", show_alert=True)
    with db.get_conn() as conn: users = conn.execute("SELECT user_id FROM users").fetchall()
    
    await c.message.edit_text("⏳ Рассылка для " + str(len(users)) + " юзеров...")
    text, media, mtype = BC_STATE.get('text', ''), BC_STATE.get('media'), BC_STATE.get('media_type')
    markup = kb.build_kb_from_rows(BC_STATE.get('buttons', []))

    ok, err = 0, 0
    for u in users:
        try:
            if media:
                if mtype == 'photo': await c.bot.send_photo(u['user_id'], media, caption=text, reply_markup=markup)
                else: await c.bot.send_video(u['user_id'], media, caption=text, reply_markup=markup)
            else: await c.bot.send_message(u['user_id'], text, reply_markup=markup)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception: err += 1

    await c.message.answer("✅ Готово.\nУспешно: " + str(ok) + "\nОшибок: " + str(err), reply_markup=kb.back_admin_kb())
    BC_STATE.clear()
    BC_STATE.update({"text": "", "media": None, "media_type": None, "limit": 0, "buttons": []})

# ================= АДМИНКА: НАСТРОЙКИ, ИНТЕГРАЦИИ, ОП =================
@dp.callback_query(F.data == "settings", IsAdminFilter())
async def admin_settings(c: CallbackQuery):
    await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=kb.settings_kb())
    await c.answer()

@dp.callback_query(F.data.startswith("set:"), IsAdminFilter())
async def set_val(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[1]
    await state.update_data(set_key=key, is_media=False)
    await c.message.edit_text("Текущее значение <b>" + key + "</b>: " + str(db.get_setting(key)) + "\n\nВведи новое значение:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)

@dp.message(AdminStates.w_set_val, IsAdminFilter())
async def save_set(m: Message, state: FSMContext):
    d = await state.get_data()
    if d.get('is_media'):
        if m.photo: val = "photo:" + m.photo[-1].file_id
        elif m.video: val = "video:" + m.video.file_id
        else: return await m.answer("Нужно фото или видео.")
        db.set_setting(d['set_key'], val)
        await m.answer("✅ Медиа сохранено!", reply_markup=kb.back_admin_kb())
    else:
        db.set_setting(d['set_key'], m.html_text.strip())
        await m.answer("✅ Настройка сохранена!", reply_markup=kb.back_admin_kb())
    await state.clear()

@dp.callback_query(F.data == "bh_menu", IsAdminFilter())
async def admin_bh(c: CallbackQuery):
    en = db.get_setting("botohub_enabled") == "1"
    status = '🟢 Вкл' if en else '🔴 Выкл'
    await c.message.edit_text("🎯 <b>ОП (Botohub)</b>\n\nСтатус: " + status + "\nКол-во на входе: <b>" + str(db.get_setting('botohub_entry_count')) + "</b>", reply_markup=kb.bh_kb(en))
    await c.answer()

@dp.callback_query(F.data == "bh_toggle", IsAdminFilter())
async def bh_toggle(c: CallbackQuery):
    cur = db.get_setting("botohub_enabled")
    db.set_setting("botohub_enabled", "0" if cur == "1" else "1")
    await admin_bh(c)

@dp.callback_query(F.data == "bh_edit_text", IsAdminFilter())
async def bh_edit_text(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь новый текст для ОП:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await state.update_data(set_key="botohub_text", is_media=False)

@dp.callback_query(F.data == "bh_edit_entry", IsAdminFilter())
async def bh_edit_entry(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Сколько каналов показывать при входе?", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await state.update_data(set_key="botohub_entry_count", is_media=False)

@dp.callback_query(F.data == "tasks_menu", IsAdminFilter())
async def admin_ints(call: CallbackQuery):
    b = InlineKeyboardBuilder()
    for i in db.get_all_integrations():
        s = "🟢" if i['status'] == 'on' else "🔴"
        b.row(InlineKeyboardButton(text=s + " " + i['name'].upper() + " (" + ('ОП' if i['role'] == 'op' else 'Задания') + ")", callback_data="int_view:" + i['name']))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await call.message.edit_text("🔌 <b>Интеграции и Сервисы</b>:", reply_markup=b.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("int_view:"), IsAdminFilter())
async def int_view(call: CallbackQuery):
    n = call.data.split(":")[1]
    i = db.get_integration(n)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 Выкл" if i['status'] == 'on' else "🟢 Вкл", callback_data="int_toggle:" + n))
    b.row(InlineKeyboardButton(text="Сменить роль", callback_data="int_role:" + n))
    b.row(InlineKeyboardButton(text="🔑 Ключ", callback_data="int_key:" + n))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="tasks_menu"))
    await call.message.edit_text("⚙️ <b>" + n.upper() + "</b>\nРоль: " + i['role'] + "\nКлюч: " + (i['api_key'] or 'По умолчанию'), reply_markup=b.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("int_toggle:"), IsAdminFilter())
async def int_toggle(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.toggle_integration(n, 'off' if i['status'] == 'on' else 'on'); await int_view(call)

@dp.callback_query(F.data.startswith("int_role:"), IsAdminFilter())
async def int_role(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.set_integration_role(n, 'tasks' if i['role'] == 'op' else 'op'); await int_view(call)

@dp.callback_query(F.data.startswith("int_key:"), IsAdminFilter())
async def int_key(call: CallbackQuery, state: FSMContext):
    n = call.data.split(":")[1]
    await state.update_data(int_name=n)
    await call.message.edit_text("Введи ключ для " + n.upper() + ":", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_int_key)

@dp.message(AdminStates.w_int_key, IsAdminFilter())
async def save_int_key(message: Message, state: FSMContext):
    d = await state.get_data()
    db.update_integration_key(d['int_name'], message.text.strip())
    await state.clear()
    await message.answer("✅ Ключ сохранен!", reply_markup=kb.back_admin_kb())

# ================= АДМИНКА: НОВЫЕ УВЕДОМЛЕНИЯ =================
@dp.callback_query(F.data == "admin_notify", IsAdminFilter())
async def admin_notify(c: CallbackQuery):
    await c.message.edit_text("🔔 <b>Авто-уведомления</b>\n\nЗдесь ты можешь создать уведомления с медиа, кнопками и своим интервалом. Бот будет отправлять их сам в фоне.", reply_markup=kb.sched_notifs_menu_kb())
    await c.answer()

@dp.callback_query(F.data == "sched_list", IsAdminFilter())
async def sched_list(c: CallbackQuery):
    with db.get_conn() as conn: notifs = conn.execute("SELECT * FROM scheduled_notifs").fetchall()
    if not notifs: return await c.message.edit_text("Список пуст.", reply_markup=kb.sched_notifs_menu_kb())
    txt = "📋 <b>Твои уведомления:</b>\n\n"
    b = InlineKeyboardBuilder()
    for n in notifs:
        short_txt = n['text'][:20] + "..." if n['text'] else "Медиа"
        txt += "#" + str(n['id']) + " | Раз в " + str(n['interval_hours']) + " ч. | " + short_txt + "\n"
        b.row(InlineKeyboardButton(text="🗑 Удалить #" + str(n['id']), callback_data="sched_del:" + str(n['id']), style="danger"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_notify"))
    await c.message.edit_text(txt, reply_markup=b.as_markup())
    await c.answer()

@dp.callback_query(F.data.startswith("sched_del:"), IsAdminFilter())
async def sched_del(c: CallbackQuery):
    nid = int(c.data.split(":")[1])
    with db.get_conn() as conn: conn.execute("DELETE FROM scheduled_notifs WHERE id = ?", (nid,)); conn.commit()
    await sched_list(c)

@dp.callback_query(F.data == "sched_add", IsAdminFilter())
async def sched_add(c: CallbackQuery, state: FSMContext):
    await state.update_data(sn_text="", sn_media="", sn_media_type="", sn_buttons=[])
    await c.message.edit_text("Отправь текст уведомления (или напиши /skip, если только медиа):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_sn_text)

@dp.message(AdminStates.w_sn_text, IsAdminFilter())
async def sched_text(m: Message, state: FSMContext):
    if m.text != "/skip": await state.update_data(sn_text=m.html_text)
    await m.answer("Отправь фото/видео (или /skip):")
    await state.set_state(AdminStates.w_sn_media)

@dp.message(AdminStates.w_sn_media, IsAdminFilter())
async def sched_media(m: Message, state: FSMContext):
    if m.photo: await state.update_data(sn_media=m.photo[-1].file_id, sn_media_type="photo")
    elif m.video: await state.update_data(sn_media=m.video.file_id, sn_media_type="video")
    elif m.text != "/skip": return await m.answer("Нужно фото/видео или /skip")
    await m.answer("Отправь кнопки:\n<code>Текст - https://url - с</code>\n(или /skip):")
    await state.set_state(AdminStates.w_sn_btn)

@dp.message(AdminStates.w_sn_btn, IsAdminFilter())
async def sched_btn(m: Message, state: FSMContext):
    if m.text != "/skip":
        rows, err = parse_bulk_buttons(m.text)
        if err: return await m.answer("❌ " + err)
        await state.update_data(sn_buttons=rows)
    await m.answer("Введи интервал в часах (например: 2, 6, 24):")
    await state.set_state(AdminStates.w_sn_interval)

@dp.message(AdminStates.w_sn_interval, IsAdminFilter())
async def sched_interval(m: Message, state: FSMContext):
    try:
        hours = int(m.text)
        d = await state.get_data()
        with db.get_conn() as conn:
            conn.execute("INSERT INTO scheduled_notifs (text, media, media_type, buttons, interval_hours) VALUES (?, ?, ?, ?, ?)", (d['sn_text'], d['sn_media'], d['sn_media_type'], json.dumps(d['sn_buttons']), hours))
            conn.commit()
        await state.clear()
        await m.answer("✅ Уведомление добавлено! Оно будет отправляться автоматически.", reply_markup=kb.back_admin_kb())
    except ValueError: await m.answer("Ошибка. Введи число.")

# ================= АДМИНКА: БЭКАП =================
@dp.callback_query(F.data == "backup_help", IsAdminFilter())
async def admin_backup(c: CallbackQuery):
    try:
        filename = "backup_" + datetime.now().strftime('%d_%m_%Y_%H_%M') + ".db"
        await c.message.answer_document(FSInputFile(DB, filename=filename), caption="💾 Бэкап БД от " + datetime.now().strftime('%d.%m.%Y %H:%M'))
    except Exception as e: await c.message.answer("Ошибка бэкапа: " + str(e))
    await c.answer()

async def daily_backup_worker():
    while True:
        try:
            now = datetime.now()
            targets = [now.replace(hour=8, minute=0, second=0, microsecond=0), now.replace(hour=20, minute=0, second=0, microsecond=0)]
            next_run = next((t for t in targets if t > now), targets[0] + timedelta(days=1))
            await asyncio.sleep((next_run - now).total_seconds())
            await bot.send_document(ADMIN_ID, FSInputFile(DB), caption="📦 <b>Авто-бэкап</b>\n" + datetime.now().strftime('%d.%m.%Y %H:%M'))
        except Exception as e:
            print("Ошибка бэкапа: " + str(e)); await asyncio.sleep(3600)

# ================= ВОРКЕР УВЕДОМЛЕНИЙ =================
async def task_notifier_worker():
    while True:
        try:
            await asyncio.sleep(60) # Проверяем каждую минуту
            with db.get_conn() as conn:
                notifs = conn.execute("SELECT * FROM scheduled_notifs").fetchall()
                users = conn.execute("SELECT user_id FROM users WHERE is_banned = 0").fetchall()
                
                now = datetime.now()
                for n in notifs:
                    last_sent = n['last_sent']
                    should_send = False
                    
                    if not last_sent: should_send = True
                    else:
                        last_dt = datetime.fromisoformat(last_sent)
                        if (now - last_dt).total_seconds() >= n['interval_hours'] * 3600: should_send = True
                            
                    if should_send:
                        markup = kb.build_kb_from_rows(json.loads(n['buttons'])) if n['buttons'] else None
                        for u in users:
                            try:
                                if n['media']:
                                    if n['media_type'] == 'photo': await bot.send_photo(u['user_id'], n['media'], caption=n['text'], reply_markup=markup)
                                    else: await bot.send_video(u['user_id'], n['media'], caption=n['text'], reply_markup=markup)
                                else: await bot.send_message(u['user_id'], n['text'], reply_markup=markup)
                                await asyncio.sleep(0.05)
                            except Exception: pass
                        
                        conn.execute("UPDATE scheduled_notifs SET last_sent = ? WHERE id = ?", (now.isoformat(), n['id']))
                        conn.commit()
        except Exception as e:
            print(f"Ошибка воркера: {e}")

# ================= ЗАПУСК =================
async def main():
    db.init_db()
    asyncio.create_task(daily_backup_worker())
    asyncio.create_task(task_notifier_worker())
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
