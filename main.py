import asyncio
import random
from datetime import datetime, timedelta
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineMLKeyboardButton
from aiogram.f))
sm.state import State, StatesGroup
dpfrom aiogram.fsm.context = import FSMContext
from Dis aiogram.enums import ParseModepatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    BOT_TOKEN, ADMIN_ID, DB, DEFAULTS, WITHDRAW_AMOUNTS,
    BOTOHUB_TOKEN, BOTOHUB_URL, PIARFLOW_TOKEN, PIARFLOW_URL,
    TGRASS_TOKEN, TGRASS_URL, TRAFSLY_TOKEN, TRAFSLY_URL
)
import database as db
import keyboards as kb

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HT()

# ================== СОСТОЯНИЯ ==================
class AdminStates(StatesGroup):
    w_p_sum = State(); w_p_act = State(); w_p_srv = State(); w_p_cnt = State()
    w_u_search = State(); w_u_bal = State()
    w_ad_code = State(); w_ad_own = State(); w_ad_prc = State()
    w_int_key = State()
    w_bc_text = State(); w_bc_media = State()

def fmt(amt):
    return f"{amt:.2f}".rstrip('0').rstrip('.') if amt % 1 else f"{amt:.0f}"

async def send_av(message, text, markup=None):
    av = db.get_setting("menu_avatar")
    if av:
        await message.answer_photo(photo=av, caption=text, reply_markup=markup)
    else:
        await message.answer(text=text, reply_markup=markup)

# ================== API: BOTOHUB (ОП) ==================
async def get_bh_tasks(uid):
    headers = {"Auth": BOTOHUB_TOKEN, "Content-Type": "application/json"}
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

# ================== API: PIARFLOW ==================
async def pf_get(uid):
    headers = {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}
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
    headers = {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}
    payload = {"user_id": uid, "links": [tid]}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{PIARFLOW_URL}/sponsors/check", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    return False

# ================== API: TGRASS ==================
async def tg_get(uid):
    headers = {"Auth": TGRASS_TOKEN}
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
    headers = {"Auth": TGRASS_TOKEN}
    payload = {"tg_user_id": uid, "offer_id": int(tid)}
    async with aiohttp.ClientSession() as s:
        async with s.post("https://tgrass.space/check", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("status") == "subscribed"
    return False

# ================== API: TRAFSLY ==================
async def tr_get(uid):
    headers = {"Auth": TRAFSLY_TOKEN}
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
    headers = {"Auth": TRAFSLY_TOKEN}
    payload = {"user_id": uid, "ads_id": tid}
    async with aiohttp.ClientSession() as s:
        async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json=payload, headers=headers) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("subscribed") is True
    return False

# ================== УНИВЕРСАЛЬНЫЙ ПОЛУЧАТЕЛЬ ЗАДАНИЙ ==================
async def get_new_task(uid):
    # Проверяем, какие сервисы включены в БД и стоят на роль "Задания"
    srv = db.get_conn().execute("SELECT name FROM integrations WHERE status = 'on' AND role = 'tasks'").fetchall()
    srv_names = [s['name'] for s in srv]
    
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
    args = message.text.split()
    ref_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    if ref_id == uid: ref_id = None

    u = db.get_user(uid)
    if u and u['is_banned']: 
        return await message.answer("🚫 Вы забанены в этом боте.")

    if db.add_user(uid, message.from_user.username, ref_id):
        if ref_id: db.create_pending_referral(uid, ref_id)
    else:
        db.update_username(uid, message.from_user.username)

    # 1. Приватка
    if db.get_setting("priv_enabled") == "1":
        await message.answer(db.get_setting("priv_text"))
        await asyncio.sleep(3)

    # 2. ОП от Botohub
    op_tasks = await get_bh_tasks(uid)
    if op_tasks:
        kb_op = kb.op_screen_kb([(t['url'], "Подписаться", t['url'], False) for t in op_tasks])
        await message.answer(db.get_setting("botohub_text"), reply_markup=kb_op)
        return

    # Если ОП нет, пропускаем
    await finish_start(message, uid)

async def finish_start(message: Message, uid: int):
    db.set_op_passed(uid)
    ref = db.confirm_referral(uid)
    if ref:
        bns = int(db.get_setting("ref_bonus"))
        db.add_balance(ref, bns)
        try: await bot.send_message(ref, f'⭐ Твой реферал прошел ОП: <b>+{bns} ⭐</b>')
        except: pass
    await send_main_menu(message)

@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery):
    op_tasks = await get_bh_tasks(call.from_user.id)
    if not op_tasks:
        try: await call.message.delete()
        except: pass
        await finish_start(call.message, call.from_user.id)
    else:
        await call.answer("Вы подписались не на все каналы!", show_alert=True)
    await call.answer()

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
    else:
        await call.message.edit_text("❌ Не выполнено.", reply_markup=kb.task_kb(task["link"]))
    await call.answer()

@dp.callback_query(F.data == "skip_task")
async def skip_task_cb(call: CallbackQuery):
    task = db.get_pending_task(call.from_user.id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено", show_alert=True)
    try: await call.message.delete()
    except: pass
    await send_next_task(call.message, call.from_user.id)

# ================== ПРОФИЛЬ И РЕФЕРАЛЫ ==================
@dp.callback_query(F.data == "menu_profile")
async def menu_profile(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    t = db.get_setting("profile_text").format(
        username=f"@{u['username']}" if u['username'] else "Юзер", 
        total_refs=db.get_pending_refs_count(u['user_id'])+db.get_confirmed_refs_count(u['user_id']), 
        total_earned=fmt(u['total_earned']), 
        balance=fmt(u['balance']), 
        user_id=u['user_id'], 
        tasks_completed=u['tasks_completed']
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
        ref_bonus=db.get_setting("ref_bonus"), 
        ref_link=link, 
        total_refs=db.get_pending_refs_count(uid)+db.get_confirmed_refs_count(uid), 
        confirmed_refs=db.get_confirmed_refs_count(uid), 
        ref_list=txt, 
        balance=fmt(u['balance'])
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

# ================== ВЫВОД ==================
@dp.callback_query(F.data == "menu_withdraw")
async def menu_withdraw(call: CallbackQuery):
    try: await call.message.delete()
    except: pass
    u = db.get_user(call.from_user.id)
    t = db.get_setting("withdraw_text").format(balance=fmt(u['balance']), amounts=", ".join(map(str, WITHDRAW_AMOUNTS)))
    await send_av(call.message, t, kb.withdraw_kb())

@dp.callback_query(F.data.startswith("wd_"))
async def process_wd(call: CallbackQuery):
    amount = float(call.data.split("_")[1])
    u = db.get_user(call.from_user.id)
    
    if u['balance'] < amount: 
        return await call.answer(f"Не хватает! Баланс: {fmt(u['balance'])}", show_alert=True)
    
    req = int(db.get_setting("withdraw_friends_required"))
    if db.get_confirmed_refs_count(u['user_id']) < req: 
        return await call.answer(f"Нужно друзей: {req}", show_alert=True)
    
    wid = db.create_withdrawal(u['user_id'], amount)
    await call.message.edit_text(f'✅ Заявка <b>#{wid}</b> на <b>{fmt(amount)}</b> ⭐ создана.\n\nСрок вывода: 5 минут — 24 часа.', reply_markup=kb.back_kb())
    await call.answer()
    # ================== АДМИНКА ==================
@dp.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_main_kb())

@dp.callback_query(F.data == "admin_back", StateFilter("*"))
async def admin_back_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=kb.admin_main_kb())
    await call.answer()

# --- ИНТЕГРАЦИИ ---
@dp.callback_query(F.data == "admin_integrations")
async def admin_ints(call: CallbackQuery):
    b = InlineKeyboardBuilder()
    for i in db.get_all_integrations():
        s = "🟢" if i['status'] == 'on' else "🔴"
        b.row(InlineKeyboardButton(text=f"{s} {i['name'].upper()} ({'ОП' if i['role']=='op' else 'Задания'})", callback_data=f"int_view:{i['name']}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await call.message.edit_text("🔌 <b>Интеграции</b>", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("int_view:"))
async def int_view(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔴 Выкл" if i['status'] == 'on' else "🟢 Вкл", callback_data=f"int_toggle:{n}"))
    b.row(InlineKeyboardButton(text="Сменить роль", callback_data=f"int_role:{n}"))
    b.row(InlineKeyboardButton(text="🔑 API Ключ", callback_data=f"int_key:{n}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_integrations"))
    await call.message.edit_text(f"⚙️ <b>{n.upper()}</b>\nРоль: {i['role']}\nКлюч: {i['api_key'] or 'Нет'}", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("int_toggle:"))
async def int_toggle(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.toggle_integration(n, 'off' if i['status'] == 'on' else 'on')
    await int_view(call)

@dp.callback_query(F.data.startswith("int_role:"))
async def int_role(call: CallbackQuery):
    n = call.data.split(":")[1]; i = db.get_integration(n)
    db.set_integration_role(n, 'tasks' if i['role'] == 'op' else 'op')
    await int_view(call)

@dp.callback_query(F.data.startswith("int_key:"))
async def int_key(call: CallbackQuery, state: FSMContext):
    n = call.data.split(":")[1]
    await state.update_data(int_name=n)
    await call.message.edit_text(f"Введи ключ для {n.upper()}:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_int_key)

@dp.message(AdminStates.w_int_key)
async def save_int_key(message: Message, state: FSMContext):
    d = await state.get_data(); db.update_integration_key(d['int_name'], message.text.strip())
    await state.clear(); await message.answer("✅ Ключ сохранен!", reply_markup=kb.back_admin_kb())

# --- ПОИСК ЮЗЕРА ---
@dp.callback_query(F.data == "admin_find_user")
async def admin_fu(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введи ID или @username:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_search)

@dp.message(AdminStates.w_u_search)
async def search_user(message: Message, state: FSMContext):
    q = message.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await message.answer("❌ Не найден.")
    t = f"👤 <b>Профиль</b>\nID: <code>{u['user_id']}</code>\nНик: @{u['username'] or '—'}\nБаланс: <b>{fmt(u['balance'])}</b> ⭐\nЗаработал: <b>{fmt(u['total_earned'])}</b>\nЗаданий: <b>{u['tasks_completed']}</b>\nБан: {'Да' if u['is_banned'] else 'Нет'}"
    await message.answer(t, reply_markup=kb.user_action_kb(u['user_id'], u['is_banned']))
    await state.clear()

@dp.callback_query(F.data.startswith("u_ban:"))
async def user_ban(call: CallbackQuery):
    uid = int(call.data.split(":")[1]); u = db.get_user(uid)
    db.toggle_ban(uid, 0 if u['is_banned'] else 1)
    await call.answer("Готово")
    await call.message.edit_text("Обновлено. Введи ID снова.")

@dp.callback_query(F.data.startswith("u_bal:"))
async def user_bal(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split(":")[1])
    await state.update_data(bal_uid=uid)
    await call.message.edit_text("Введи сумму (например 50 или -20):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)

@dp.message(AdminStates.w_u_bal)
async def save_bal(message: Message, state: FSMContext):
    try:
        a = float(message.text); d = await state.get_data()
        db.add_balance(d['bal_uid'], a)
        await message.answer("✅ Баланс изменен!", reply_markup=kb.back_admin_kb())
    except: await message.answer("Ошибка.")
    await state.clear()

# --- ПРОМОКОДЫ ---
@dp.callback_query(F.data == "admin_promos")
async def admin_pr(c: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Обычный", callback_data="promo_create_normal"))
    b.row(InlineKeyboardButton(text="➕ С ОП", callback_data="promo_create_op"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("promo_create_"))
async def promo_create(c: CallbackQuery, state: FSMContext):
    is_op = 1 if "op" in c.data else 0
    await state.update_data(is_op=is_op)
    await c.message.edit_text("Введи сумму чека (звезды):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_p_sum)

@dp.message(AdminStates.w_p_sum)
async def promo_sum(m: Message, state: FSMContext):
    try:
        await state.update_data(p_amount=float(m.text))
        await m.answer("Сколько активаций?")
        await state.set_state(AdminStates.w_p_act)
    except: await m.answer("Ошибка.")

@dp.message(AdminStates.w_p_act)
async def promo_act(m: Message, state: FSMContext):
    try:
        await state.update_data(p_uses=int(m.text)); d = await state.get_data()
        if d['is_op']:
            await m.answer("Какой сервис? (botohub, subgram, flyer):")
            await state.set_state(AdminStates.w_p_srv)
        else:
            code = "promo_" + str(random.randint(100000, 999999))
            db.create_promo(code, d['p_amount'], d['p_uses'], is_op=0)
            me = await bot.get_me()
            await m.answer(f"✅ Чек создан!\nСсылка: https://t.me/{me.username}?start={code}", reply_markup=kb.back_admin_kb())
            await state.clear()
    except: await m.answer("Ошибка.")

@dp.message(AdminStates.w_p_srv)
async def promo_srv(m: Message, state: FSMContext):
    await state.update_data(p_srv=m.text.lower())
    await m.answer("Сколько спонсоров пройти?")
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

# --- РЕКЛАМА ---
@dp.callback_query(F.data == "admin_ads")
async def admin_ads(c: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Создать метку", callback_data="ad_create"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("📊 <b>Реклама</b>", reply_markup=b.as_markup())

@dp.callback_query(F.data == "ad_create")
async def ad_create(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи код метки (например tiktok):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_ad_code)

@dp.message(AdminStates.w_ad_code)
async def ad_code(m: Message, state: FSMContext):
    await state.update_data(ad_code=m.text.lower())
    await m.answer("Введи ID или @username рекламодателя:")
    await state.set_state(AdminStates.w_ad_own)

@dp.message(AdminStates.w_ad_own)
async def ad_own(m: Message, state: FSMContext):
    q = m.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await m.answer("Не найден.")
    await state.update_data(ad_own=u['user_id'])
    await m.answer("Введи цену за переход (число):")
    await state.set_state(AdminStates.w_ad_prc)

@dp.message(AdminStates.w_ad_prc)
async def ad_prc(m: Message, state: FSMContext):
    try:
        d = await state.get_data(); prc = float(m.text)
        db.add_ad_source(d['ad_code'], d['ad_own'], prc)
        me = await bot.get_me()
        await m.answer(f"✅ Метка создана!\nСсылка: https://t.me/{me.username}?start=ad_{d['ad_code']}\nСтат: /stat_{d['ad_code']}", reply_markup=kb.back_admin_kb())
        await state.clear()
    except: await m.answer("Ошибка.")

# --- БЭКАП ---
@dp.callback_query(F.data == "admin_backup")
async def admin_backup(c: CallbackQuery):
    try:
        doc = FSInputFile(DB)
        await c.message.answer_document(doc, caption="💾 Бэкап БД")
    except Exception as e: await c.message.answer(f"Ошибка: {e}")
    await c.answer()
    # ================== РАССЫЛКА ==================
BC_STATE = {}

@dp.callback_query(F.data == "admin_broadcast")
async def bc_menu(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Текст", callback_data="bc_edit_text"))
    b.row(InlineKeyboardButton(text="📎 Медиа", callback_data="bc_edit_media"))
    b.row(InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bc_preview"))
    b.row(InlineKeyboardButton(text="✅ Отправить", callback_data="bc_start"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await c.message.edit_text("📢 <b>Рассылка</b>", reply_markup=b.as_markup())

@dp.callback_query(F.data == "bc_edit_text")
async def bc_edit_text(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь текст (можно с HTML):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_text)

@dp.message(AdminStates.w_bc_text)
async def bc_save_text(m: Message, state: FSMContext):
    BC_STATE['text'] = m.html_text
    await m.answer("✅ Текст сохранен!", reply_markup=kb.back_admin_kb())
    await state.clear()

@dp.callback_query(F.data == "bc_edit_media")
async def bc_edit_media(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Отправь фото или видео:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_bc_media)

@dp.message(AdminStates.w_bc_media)
async def bc_save_media(m: Message, state: FSMContext):
    if m.photo: BC_STATE['media'] = ('photo', m.photo[-1].file_id)
    elif m.video: BC_STATE['media'] = ('video', m.video.file_id)
    else: return await m.answer("Нужно фото или видео.")
    await m.answer("✅ Медиа сохранено!", reply_markup=kb.back_admin_kb())
    await state.clear()

@dp.callback_query(F.data == "bc_preview")
async def bc_preview(c: CallbackQuery):
    text = BC_STATE.get('text', '')
    media = BC_STATE.get('media')
    if not text and not media: return await c.answer("Пусто", show_alert=True)
    
    if media:
        if media[0] == 'photo': await c.message.answer_photo(media[1], caption=text)
        else: await c.message.answer_video(media[1], caption=text)
    else: await c.message.answer(text)

@dp.callback_query(F.data == "bc_start")
async def bc_start(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return
    users = db.get_conn().execute("SELECT user_id FROM users").fetchall()
    await c.message.edit_text(f"⏳ Рассылка для {len(users)} юзеров...")
    
    text = BC_STATE.get('text', '')
    media = BC_STATE.get('media')
    ok, err = 0, 0
    
    for u in users:
        try:
            if media:
                if media[0] == 'photo': await c.bot.send_photo(u['user_id'], media[1], caption=text)
                else: await c.bot.send_video(u['user_id'], media[1], caption=text)
            else: await c.bot.send_message(u['user_id'], text)
            ok += 1
            await asyncio.sleep(0.05) # Задержка для избежания лимитов
        except: err += 1
    
    await c.message.answer(f"✅ Готово.\nУспешно: {ok}\nОшибок: {err}", reply_markup=kb.back_admin_kb())
    BC_STATE.clear()

# ================== СТАТИСТИКА РЕКЛАМЫ (по команде /stat_CODE) ==================
@dp.message(F.text.startswith("/stat_"))
async def ad_stat_cmd(m: Message):
    code = m.text.split("_")[1].lower()
    src = db.get_ad_source(code)
    if not src: return await m.answer("❌ Метка не найдена.")
    
    with db.get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ?", (code,)).fetchone()[0]
        passed_op = conn.execute("SELECT COUNT(*) FROM users WHERE ad_code = ? AND passed_op = 1", (code,)).fetchone()[0]
        tasks = conn.execute("SELECT COUNT(*) FROM task_completed tc JOIN users u ON tc.user_id = u.user_id WHERE u.ad_code = ?", (code,)).fetchone()[0]
        earned = conn.execute("SELECT SUM(balance) FROM users WHERE ad_code = ?", (code,)).fetchone()[0] or 0.0
        withdrawn = conn.execute("SELECT SUM(amount) FROM withdrawals w JOIN users u ON w.user_id = u.user_id WHERE u.ad_code = ? AND w.status = 'completed'", (code,)).fetchone()[0] or 0.0
    
    text = (
        f"📊 <b>Статистика метки: {code}</b>\n\n"
        f"👤 Переходов: <b>{src['clicks']}</b>\n"
        f"🆕 Зарегалось: <b>{total_users}</b>\n"
        f"✅ Прошли ОП: <b>{passed_op}</b>\n"
        f"🎯 Заданий выполнено: <b>{tasks}</b>\n"
        f"💰 Заработали: <b>{fmt(earned)}</b> ⭐\n"
        f"💸 Вывели: <b>{fmt(withdrawn)}</b> ⭐\n\n"
        f"💵 Цена перехода: <b>{src['price']} ₽</b>\n"
        f"👤 Рекламодатель: <code>{src['owner_id']}</code>"
    )
    
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔄 Обновить", callback_data=f"upd_stat:{code}"))
    await m.answer(text, reply_markup=b.as_markup())

@dp.callback_query(F.data.startswith("upd_stat:"))
async def upd_stat(c: CallbackQuery):
    # Эмулируем вызов команды заново для обновления
    c.message.text = f"/stat_{c.data.split(':')[1]}"
    await ad_stat_cmd(c.message)
    await c.answer("Обновлено")

# ================== АВТО-БЭКАП ==================
async def daily_backup_worker():
    while True:
        try:
            now = datetime.now()
            # Время бэкапа: 08:00 и 20:00
            targets = [now.replace(hour=8, minute=0, second=0, microsecond=0), now.replace(hour=20, minute=0, second=0, microsecond=0)]
            next_run = next((t for t in targets if t > now), targets[0] + timedelta(days=1))
            wait_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            doc = FSInputFile(DB)
            await bot.send_document(ADMIN_ID, doc, caption=f"📦 <b>Авто-бэкап</b>\n{datetime.now().strftime('%d.%m.%Y %H:%M')}")
        except Exception as e:
            print(f"Ошибка бэкапа: {e}")
            await asyncio.sleep(3600)

# ================== ЗАПУСК ==================
async def main():
    db.init_db()
    asyncio.create_task(daily_backup_worker())
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
