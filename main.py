import asyncio, logging, random, json, os, shutil
from datetime import datetime
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
    async def __call__(self, event) -> bool: return event.from_user.id == ADMIN_ID

def fmt(amt): return f"{round(amt, 2):g}" if amt % 1 else f"{round(amt):g}"
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
    try: await message.answer(text=text, reply_markup=markup)
    except Exception as e: print(f"Ошибка отправки: {e}")

class UserStates(StatesGroup):
    w_amount = State()

class AdminStates(StatesGroup):
    w_sp_name = State(); w_sp_url = State(); w_sp_chat = State()
    w_t_name = State(); w_t_url = State(); w_t_chat = State(); w_t_reward = State()
    w_u_search = State(); w_u_bal = State()
    w_set_val = State()
    w_n_text = State(); w_n_media = State(); w_n_btns = State(); w_n_int = State()

async def pf_get(uid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{PIARFLOW_URL}/sponsors", json={"user_id": uid, "chat_id": uid, "max_sponsors": 1}, headers={"Authorization": f"Bearer {PIARFLOW_TOKEN}"}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp and sp[0].get("status") == "unsubscribed": return {"srv": "piarflow", "tid": sp[0]["link"], "link": sp[0]["link"]}
    except Exception: pass
    return None

async def pf_check(uid, tid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{PIARFLOW_URL}/sponsors/check", json={"user_id": uid, "links": [tid]}, headers={"Authorization": f"Bearer {PIARFLOW_TOKEN}"}) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    except Exception: pass
    return False

async def tg_get(uid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://tgrass.space/tasks", json={"tg_user_id": uid, "is_premium": False, "lang": "ru"}, headers={"Auth": TGRASS_TOKEN}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "not_ok" and d.get("offers"):
                        for offer in d["offers"]:
                            if not offer.get("subscribed"): return {"srv": "tgrass", "tid": str(offer["offer_id"]), "link": offer["link"]}
    except Exception: pass
    return None

async def tg_check(uid, tid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://tgrass.space/check", json={"tg_user_id": uid, "offer_id": int(tid)}, headers={"Auth": TGRASS_TOKEN}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    if d.get("status") == "subscribed": return True
    except Exception: pass
    return False

async def tr_get(uid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.trafsly.com/api/v1/get-sponsors", json={"user_id": uid}, headers={"Auth": TRAFSLY_TOKEN}, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    sp = d.get("sponsors", [])
                    if sp and d.get("status") == "warning": return {"srv": "trafsly", "tid": str(sp[0]["ads_id"]), "link": sp[0]["link"]}
    except Exception: pass
    return None

async def tr_check(uid, tid):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.trafsly.com/api/v1/confirm-subscription", json={"user_id": uid, "ads_id": tid}, headers={"Auth": TRAFSLY_TOKEN}) as r:
                if r.status == 200:
                    d = await r.json()
                    return d.get("subscribed") is True
    except Exception: pass
    return False

async def get_new_task(uid):
    for fn in (tg_get, pf_get, tr_get):
        try:
            t = await fn(uid)
            if t and str(t.get("link", "")).startswith("http"): return t
        except Exception: pass
    return None

async def check_task_status(srv, uid, tid):
    if srv == "piarflow": return await pf_check(uid, tid)
    if srv == "tgrass": return await tg_check(uid, tid)
    if srv == "trafsly": return await tr_check(uid, tid)
    return False

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
            msg = f'<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> <b>Новый реферал!</b> Пользователь <b>{uname}</b> запустил бота по вашей ссылке.\nВы получаете <b>{db.get_setting("ref_percent")}%</b> от его заработка!'
            try: await bot.send_message(ref_id, msg)
            except Exception: pass
    else:
        db.update_username(uid, message.from_user.username)

    if not await check_user_sponsors(uid):
        sponsors = db.get_sponsors()
        valid = [s for s in sponsors if s['name'] and s['url']]
        if not valid: return await send_main_menu(message)
        sp_list = "\n".join([f"├ {s['name']}" for s in valid])
        txt = safe_format(db.get_setting("sponsor_text"), sponsors=sp_list)
        return await message.answer(txt, reply_markup=kb.sponsor_kb(valid))

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

@dp.message(Command("diag"), IsAdminFilter())
async def diag_cmd(message: Message):
    uid = message.from_user.id
    checks = [
        ("PiarFlow", bool(PIARFLOW_TOKEN), f"{PIARFLOW_URL}/sponsors", {"user_id": uid, "chat_id": uid, "max_sponsors": 1}, {"Authorization": f"Bearer {PIARFLOW_TOKEN}"}),
        ("Tgrass", bool(TGRASS_TOKEN), "https://tgrass.space/tasks", {"tg_user_id": uid, "is_premium": False, "lang": "ru"}, {"Auth": TGRASS_TOKEN}),
        ("Trafsly", bool(TRAFSLY_TOKEN), "https://api.trafsly.com/api/v1/get-sponsors", {"user_id": uid}, {"Auth": TRAFSLY_TOKEN}),
    ]
    out = []
    async with aiohttp.ClientSession() as s:
        for name, has_token, url, payload, headers in checks:
            if not has_token:
                out.append(f"{name}: токен пустой (проверь переменные в BotHost)")
                continue
            try:
                async with s.post(url, json=payload, headers=headers, timeout=10) as r:
                    body = (await r.text())[:200].replace("\n", " ")
                    out.append(f"{name}: HTTP {r.status}\n{body}")
            except Exception as e:
                out.append(f"{name}: ОШИБКА {type(e).__name__}: {e}")
    await message.answer("\n\n".join(out), parse_mode=None)

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

@dp.callback_query(F.data == "menu_instruction")
async def menu_instruction(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    await send_av(call.message, db.get_setting("instruction_text"), kb.back_kb())
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
        if task and not str(task['link']).startswith("http"):
            db.mark_task_status(task['id'], 'skipped')
            task = None
        if task:
            txt = safe_format(db.get_setting("task_text"), reward=fmt(task['reward']))
            if task['service'] == "custom":
                return await message.answer(txt, reply_markup=kb.task_kb(task['link'], "custom", task['task_id']))
            else:
                return await message.answer(txt, reply_markup=kb.task_kb(task['link'], "service"))
        
        custom_tasks = db.get_custom_tasks()
        for ct in custom_tasks:
            if not str(ct['url']).startswith("http"): continue
            if not db.check_user_channel(uid, ct['chat_id']):
                db.save_task(uid, "custom", str(ct['id']), ct['url'], ct['reward'])
                task = db.get_pending_task(uid)
                txt = safe_format(db.get_setting("task_text"), reward=fmt(task['reward']))
                return await message.answer(txt, reply_markup=kb.task_kb(task['link'], "custom", task['task_id']))
                
        new_t = await get_new_task(uid)
        if new_t:
            reward = float(db.get_setting("task_reward"))
            db.save_task(uid, new_t["srv"], new_t["tid"], new_t["link"], reward)
            task = db.get_pending_task(uid)
            txt = safe_format(db.get_setting("task_text"), reward=fmt(task['reward']))
            return await message.answer(txt, reply_markup=kb.task_kb(task['link'], "service"))

        await message.answer("😔 На данный момент нет доступных заданий.", reply_markup=kb.back_kb())
    except Exception as e:
        print(f"Ошибка выдачи задания: {e}")
        await message.answer("😔 Ошибка загрузки. Попробуйте позже.", reply_markup=kb.back_kb())

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
        db.mark_task_status(task['id'], 'done')
        db.add_balance(uid, task['reward'])
        db.add_task_completed(uid)
        db.mark_user_channel(uid, "service_" + task['service'], "service")
        
        u = db.get_user(uid)
        if u['referrer_id']:
            ref_bonus = round(task['reward'] * (float(db.get_setting("ref_percent")) / 100), 2)
            if ref_bonus > 0:
                db.add_ref_earning(u['referrer_id'], ref_bonus)
                try: await bot.send_message(u['referrer_id'], f"⚡️ Твой реферал выполнил задание. Тебе начислено <b>{fmt(ref_bonus)}</b> ⭐")
                except Exception: pass

        try: await call.message.edit_text(f"✅ Выполнено! Начислено: {fmt(task['reward'])} ⭐")
        except Exception: pass
        await asyncio.sleep(1)
        try: await call.message.delete()
        except Exception: pass
        await send_next_task(call.message, uid)
    else:
        db.mark_task_status(task['id'], 'manual')
        try: await call.message.delete()
        except Exception: pass
        await call.message.answer("⏳ Задание отправлено на ручную проверку. Ожидайте зачисления. А пока можете выполнить следующее:", reply_markup=kb.back_kb())
        await send_next_task(call.message, uid)
        await call.answer("На проверке. Ожидайте!", show_alert=True)

@dp.callback_query(F.data.startswith("check_custom:"))
async def check_custom_cb(call: CallbackQuery):
    uid = call.from_user.id
    tid = call.data.split(":")[1]
    task = db.get_pending_task(uid)
    if not task or task['task_id'] != tid: return await call.answer("Задание не найдено.", show_alert=True)
    ct = next((x for x in db.get_custom_tasks() if str(x['id']) == tid), None)
    if not ct: return await call.answer("Задание удалено.", show_alert=True)

    try: await call.message.edit_text("⏳ Проверяем...")
    except Exception: pass
    
    try:
        member = await bot.get_chat_member(ct['chat_id'], uid)
        is_done = member.status not in ['left', 'kicked']
    except Exception: is_done = False

    if is_done:
        db.mark_task_status(task['id'], 'done')
        db.add_balance(uid, task['reward'])
        db.add_task_completed(uid)
        db.mark_user_channel(uid, ct['chat_id'], "custom")
        try: await call.message.edit_text(f"✅ Выполнено! Начислено: {fmt(task['reward'])} ⭐")
        except Exception: pass
        await asyncio.sleep(1)
        try: await call.message.delete()
        except Exception: pass
        await send_next_task(call.message, uid)
    else:
        try: await call.message.edit_text("❌ Вы не подписались.", reply_markup=kb.task_kb(ct['url'], "custom", tid))
        except Exception: await call.answer("❌ Вы не подписались.", show_alert=True)
    await call.answer()

@dp.callback_query(F.data == "skip_task")
async def skip_task_cb(call: CallbackQuery):
    task = db.get_pending_task(call.from_user.id)
    if task: db.mark_task_status(task['id'], 'skipped')
    await call.answer("Пропущено")
    try: await call.message.delete()
    except Exception: pass
    await send_next_task(call.message, call.from_user.id)

@dp.callback_query(F.data == "menu_profile")
async def menu_profile(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    u = db.get_user(call.from_user.id)
    uname = "@" + u['username'] if u['username'] else "Юзер"
    t = safe_format(db.get_setting("profile_text"), username=uname, total_refs=db.get_refs_count(u['user_id']), total_withdrawn=fmt(u['total_withdrawn']), balance=fmt(u['balance']), user_id=u['user_id'], tasks_completed=u['tasks_completed'], ref_earnings=fmt(u['ref_earnings']))
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
    t = safe_format(db.get_setting("ref_text"), ref_percent=db.get_setting("ref_percent"), ref_link=link, total_refs=db.get_refs_count(uid), ref_earnings=fmt(u['ref_earnings']))
    await send_av(call.message, t, kb.back_kb())
    await call.answer()

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
    if round(u['balance'], 2) < amount: return await message.answer(f"❌ Не хватает. Баланс: {fmt(u['balance'])} ⭐")
    wid = db.create_withdrawal(uid, amount)
    if not wid: return await message.answer("❌ Не хватает средств.")
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

@dp.callback_query(F.data == "menu_stats")
async def menu_stats(call: CallbackQuery):
    try: await call.message.delete()
    except Exception: pass
    await call.message.answer("📊 <b>Статистика</b>\n\nВыбери раздел:", reply_markup=kb.stats_kb())
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
async def admin_stats(c: CallbackQuery):
    s = db.get_stats()
    txt = f"📊 <b>Статистика</b>\n\n👥 Юзеров: {s['total']}\n🆕 Сегодня: {s['today']}\n💰 Баланс: {fmt(s['total_bal'])}⭐\n💸 В заявках: {fmt(s['pending_wd'])}⭐"
    try: await c.message.edit_text(txt, reply_markup=kb.back_admin_kb())
    except Exception: pass
    await c.answer()

@dp.callback_query(F.data == "admin_sponsors", IsAdminFilter())
async def admin_sponsors(c: CallbackQuery):
    try: await c.message.edit_text("🎯 <b>Обязательные спонсоры (Вход)</b>\nНажми на 🗑 для удаления:", reply_markup=kb.admin_sponsors_kb(db.get_sponsors()))
    except Exception: pass
    await c.answer()

@dp.callback_query(F.data == "sp_add", IsAdminFilter())
async def sp_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("1️⃣ Введи название канала:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_sp_name)
    await c.answer()

@dp.message(AdminStates.w_sp_name, IsAdminFilter())
async def sp_name(m: Message, state: FSMContext):
    await state.update_data(sp_name=m.text)
    await m.answer("2️⃣ Введи ссылку (https://t.me/...):")
    await state.set_state(AdminStates.w_sp_url)

@dp.message(AdminStates.w_sp_url, IsAdminFilter())
async def sp_url(m: Message, state: FSMContext):
    if not m.text.startswith("http"): return await m.answer("❌ Ссылка должна начинаться с http://")
    await state.update_data(sp_url=m.text)
    await m.answer("3️⃣ Перешли ЛЮБОЙ пост из этого канала:\n⚠️ <i>Бот должен быть админом!</i>")
    await state.set_state(AdminStates.w_sp_chat)

@dp.message(AdminStates.w_sp_chat, IsAdminFilter())
async def sp_chat(m: Message, state: FSMContext):
    chat_id = None
    if m.forward_origin and m.forward_origin.type == 'channel': chat_id = m.forward_origin.chat.id
    elif m.forward_from_chat: chat_id = m.forward_from_chat.id
    if not chat_id: return await m.answer("❌ Перешли именно пост из канала.")
    d = await state.get_data()
    db.add_sponsor(d['sp_name'], d['sp_url'], str(chat_id))
    await state.clear()
    await m.answer("✅ Спонсор добавлен!", reply_markup=kb.admin_kb())

@dp.callback_query(F.data.startswith("sp_del:"), IsAdminFilter())
async def sp_del(c: CallbackQuery):
    db.del_sponsor(int(c.data.split(":")[1]))
    await c.answer("Удален")
    await admin_sponsors(c)

@dp.callback_query(F.data == "admin_tasks", IsAdminFilter())
async def admin_tasks(c: CallbackQuery):
    try: await c.message.edit_text("💼 <b>Свои задания (Каналы)</b>\nНажми на 🗑 для удаления:", reply_markup=kb.admin_tasks_kb(db.get_custom_tasks()))
    except Exception: pass
    await c.answer()

@dp.callback_query(F.data == "task_add", IsAdminFilter())
async def task_add(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("1️⃣ Введи название канала:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_t_name)
    await c.answer()

@dp.message(AdminStates.w_t_name, IsAdminFilter())
async def t_name(m: Message, state: FSMContext):
    await state.update_data(t_name=m.text)
    await m.answer("2️⃣ Введи ссылку (https://t.me/...):")
    await state.set_state(AdminStates.w_t_url)

@dp.message(AdminStates.w_t_url, IsAdminFilter())
async def t_url(m: Message, state: FSMContext):
    if not m.text.startswith("http"): return await m.answer("❌ Ссылка должна начинаться с http://")
    await state.update_data(t_url=m.text)
    await m.answer("3️⃣ Перешли ЛЮБОЙ пост из этого канала:")
    await state.set_state(AdminStates.w_t_chat)

@dp.message(AdminStates.w_t_chat, IsAdminFilter())
async def t_chat(m: Message, state: FSMContext):
    chat_id = None
    if m.forward_origin and m.forward_origin.type == 'channel': chat_id = m.forward_origin.chat.id
    elif m.forward_from_chat: chat_id = m.forward_from_chat.id
    if not chat_id: return await m.answer("❌ Перешли именно пост из канала.")
    await state.update_data(t_chat=str(chat_id))
    await m.answer("4️⃣ Введи награду за подписку (в звездах, например: 1.5):")
    await state.set_state(AdminStates.w_t_reward)

@dp.message(AdminStates.w_t_reward, IsAdminFilter())
async def t_reward(m: Message, state: FSMContext):
    try:
        reward = float(m.text)
        d = await state.get_data()
        db.add_custom_task(d['t_name'], d['t_url'], d['t_chat'], reward)
        await state.clear()
        await m.answer("✅ Задание добавлено!", reply_markup=kb.admin_kb())
    except ValueError: await m.answer("❌ Введи число.")

@dp.callback_query(F.data.startswith("task_del:"), IsAdminFilter())
async def task_del(c: CallbackQuery):
    db.del_custom_task(int(c.data.split(":")[1]))
    await c.answer("Удалено")
    await admin_tasks(c)

@dp.callback_query(F.data == "admin_wd", IsAdminFilter())
async def admin_wd(c: CallbackQuery):
    wds = db.get_pending_withdrawals()
    if not wds: return await c.message.edit_text("Заявок нет.", reply_markup=kb.back_admin_kb())
    w = wds[0]
    u = db.get_user(w['user_id'])
    uname = "@" + u['username'] if u['username'] else "id" + str(u['user_id'])
    txt = f"💸 <b>Заявка #{w['id']}</b>\n\n👤 {uname} (<code>{u['user_id']}</code>)\n💰 Сумма: <b>{fmt(w['amount'])}</b> ⭐\n👥 Рефов: {db.get_refs_count(u['user_id'])}\n🎯 Заданий: {u['tasks_completed']}"
    try: await c.message.edit_text(txt, reply_markup=kb.wd_kb(w['id']))
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

@dp.callback_query(F.data == "admin_user", IsAdminFilter())
async def admin_user(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("Введи ID или @username:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_search)
    await c.answer()

@dp.message(AdminStates.w_u_search, IsAdminFilter())
async def admin_u_search(m: Message, state: FSMContext):
    q = m.text.strip()
    u = db.get_user(int(q)) if q.isdigit() else db.get_user_by_username(q)
    if not u: return await m.answer("❌ Не найден.")
    txt = f"👤 <b>Профиль</b>\nID: <code>{u['user_id']}</code>\nБаланс: {fmt(u['balance'])}⭐\nДолг: {fmt(u['debt'])}⭐\nБан: {'Да' if u['is_banned'] else 'Нет'}"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Разбанить" if u['is_banned'] else "🚫 Забанить", callback_data=f"u_ban:{u['user_id']}"))
    b.row(InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"u_bal:{u['user_id']}"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await m.answer(txt, reply_markup=b.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("u_ban:"), IsAdminFilter())
async def admin_u_ban(c: CallbackQuery):
    uid = int(c.data.split(":")[1])
    u = db.get_user(uid)
    db.toggle_ban(uid, 0 if u['is_banned'] else 1)
    await c.answer("Статус обновлен")

@dp.callback_query(F.data.startswith("u_bal:"), IsAdminFilter())
async def admin_u_bal(c: CallbackQuery, state: FSMContext):
    await state.update_data(bal_uid=int(c.data.split(":")[1]))
    await c.message.edit_text("Введи сумму (например: 50 или -20):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_u_bal)
    await c.answer()

@dp.message(AdminStates.w_u_bal, IsAdminFilter())
async def admin_u_bal_save(m: Message, state: FSMContext):
    try:
        d = await state.get_data()
        db.add_balance(d['bal_uid'], float(m.text))
        await m.answer("✅ Баланс изменен!", reply_markup=kb.admin_kb())
        await state.clear()
    except Exception: await m.answer("Ошибка. Введи число.")

@dp.callback_query(F.data == "admin_settings", IsAdminFilter())
async def admin_settings(c: CallbackQuery):
    await c.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=kb.settings_kb(db.get_setting('ref_percent'), db.get_setting('task_reward'), db.get_setting('sponsor_penalty')))
    await c.answer()

@dp.callback_query(F.data.startswith("set:"), IsAdminFilter())
async def admin_set(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[1]
    await state.update_data(set_key=key)
    await c.message.edit_text(f"Введи новое значение для <b>{key}</b>:", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_set_val)
    await c.answer()

@dp.message(AdminStates.w_set_val, IsAdminFilter())
async def admin_set_save(m: Message, state: FSMContext):
    d = await state.get_data()
    db.set_setting(d['set_key'], m.html_text.strip())
    await m.answer("✅ Сохранено!", reply_markup=kb.admin_kb())
    await state.clear()

@dp.callback_query(F.data == "admin_backup", IsAdminFilter())
async def admin_backup(c: CallbackQuery):
    await c.message.edit_text("📦 <b>Бэкап</b>\n\nСкачай файл или просто отправь сюда .db файл для восстановления.", reply_markup=kb.backup_kb())
    await c.answer()

@dp.callback_query(F.data == "backup_download", IsAdminFilter())
async def backup_download(c: CallbackQuery):
    try:
        filename = "backup_" + datetime.now().strftime('%d_%m_%Y_%H_%M') + ".db"
        await c.message.answer_document(FSInputFile(DB, filename=filename), caption="💾 Твой бэкап")
    except Exception as e: await c.message.answer(f"Ошибка: {e}")
    await c.answer()

@dp.message(F.document, IsAdminFilter())
async def backup_upload(message: Message):
    if not message.document.file_name.endswith(".db"): return await message.answer("❌ Нужен .db файл")
    file_path = f"/tmp/{message.document.file_name}"
    await bot.download(message.document, destination=file_path)
    try:
        shutil.copy(file_path, DB)
        await message.answer("✅ База загружена! Перезапусти бота в панели BotHost.")
    except Exception as e: await message.answer(f"Ошибка: {e}")

@dp.callback_query(F.data == "admin_notify", IsAdminFilter())
async def admin_notify(c: CallbackQuery):
    await c.message.edit_text("🔔 <b>Уведомления</b>", reply_markup=kb.notify_menu_kb(db.get_notifies()))
    await c.answer()

@dp.callback_query(F.data.startswith("notify_del:"), IsAdminFilter())
async def notify_del(c: CallbackQuery):
    db.del_notify(int(c.data.split(":")[1]))
    await c.answer("Удалено")
    await admin_notify(c)

@dp.callback_query(F.data == "notify_add", IsAdminFilter())
async def notify_add(c: CallbackQuery, state: FSMContext):
    await state.update_data(n_text="", n_media="", n_mtype="", n_btns="[]")
    await c.message.edit_text("Отправь текст (или напиши /skip):", reply_markup=kb.back_admin_kb())
    await state.set_state(AdminStates.w_n_text)
    await c.answer()

@dp.message(AdminStates.w_n_text, IsAdminFilter())
async def n_text(m: Message, state: FSMContext):
    if m.text != "/skip": await state.update_data(n_text=m.html_text)
    await m.answer("Отправь фото/видео (или /skip):")
    await state.set_state(AdminStates.w_n_media)

@dp.message(AdminStates.w_n_media, IsAdminFilter())
async def n_media(m: Message, state: FSMContext):
    if m.photo: await state.update_data(n_media=m.photo[-1].file_id, n_mtype="photo")
    elif m.video: await state.update_data(n_media=m.video.file_id, n_mtype="video")
    elif m.text != "/skip": return await m.answer("Нужно фото/видео или /skip")
    await m.answer("Отправь ссылки для кнопок (или /skip):")
    await state.set_state(AdminStates.w_n_btns)

@dp.message(AdminStates.w_n_btns, IsAdminFilter())
async def n_btns(m: Message, state: FSMContext):
    if m.text != "/skip":
        await state.update_data(n_btns=json.dumps([[{"text": "Кнопка", "url": m.text, "color": "primary"}]]))
    await m.answer("Введи интервал в часах (например 12):")
    await state.set_state(AdminStates.w_n_int)

@dp.message(AdminStates.w_n_int, IsAdminFilter())
async def n_int(m: Message, state: FSMContext):
    try:
        h = int(m.text)
        d = await state.get_data()
        db.add_notify(d['n_text'], d['n_media'], d['n_mtype'], d['n_btns'], h)
        await state.clear()
        await m.answer("✅ Уведомление добавлено!", reply_markup=kb.admin_kb())
    except Exception: await m.answer("Ошибка. Введи число.")
async def manual_check_worker():
    while True:
        await asyncio.sleep(300)
        try:
            tasks = db.get_manual_tasks()
            for t in tasks:
                uid = t['user_id']
                is_done = await check_task_status(t['service'], uid, t['task_id'])
                if is_done:
                    db.mark_task_status(t['id'], 'done')
                    db.add_balance(uid, t['reward'])
                    db.add_task_completed(uid)
                    u = db.get_user(uid)
                    if u['referrer_id']:
                        ref_bonus = round(t['reward'] * (float(db.get_setting("ref_percent")) / 100), 2)
                        if ref_bonus > 0: db.add_ref_earning(u['referrer_id'], ref_bonus)
                    try: await bot.send_message(uid, f"✅ Задание подтверждено! +{fmt(t['reward'])} ⭐")
                    except Exception: pass
        except Exception: pass

async def sponsor_check_worker():
    while True:
        await asyncio.sleep(3600)
        try:
            sponsors = db.get_sponsors()
            if not sponsors: continue
            with db.get_conn() as conn: users = conn.execute("SELECT * FROM users").fetchall()
            for u in users:
                for s in sponsors:
                    try:
                        member = await bot.get_chat_member(s['chat_id'], u['user_id'])
                        if member.status in ['left', 'kicked']:
                            if db.check_user_channel(u['user_id'], s['chat_id']):
                                with db.get_conn() as conn:
                                    conn.execute("DELETE FROM user_channels WHERE user_id=? AND chat_id=?", (u['user_id'], s['chat_id']))
                                    conn.commit()
                                
                                penalty = float(db.get_setting("sponsor_penalty"))
                                if penalty > 0:
                                    db.add_balance(u['user_id'], -penalty)
                                    try: await bot.send_message(u['user_id'], f"❌ Вы отписались от <b>{s['name']}</b>. Списано {fmt(penalty)} ⭐.")
                                    except Exception: pass
                                    if u['referrer_id']:
                                        db.add_balance(u['referrer_id'], -penalty)
                                        try: await bot.send_message(u['referrer_id'], f"⚠️ Реферал отписался от <b>{s['name']}</b>. Списано {fmt(penalty)} ⭐.")
                                        except Exception: pass
                    except Exception: pass
        except Exception: pass

async def notifier_worker():
    while True:
        await asyncio.sleep(60)
        try:
            notifies = db.get_notifies()
            now = datetime.now()
            for n in notifies:
                if not n['last_sent'] or (now - datetime.fromisoformat(n['last_sent'])).total_seconds() >= n['interval_h'] * 3600:
                    with db.get_conn() as conn: users = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
                    for u in users:
                        try:
                            if n['media']:
                                if n['mtype'] == 'photo': await bot.send_photo(u['user_id'], n['media'], caption=n['text'])
                                else: await bot.send_video(u['user_id'], n['media'], caption=n['text'])
                            else: await bot.send_message(u['user_id'], n['text'])
                            await asyncio.sleep(0.05)
                        except Exception: pass
                    db.update_notify_time(n['id'], now.isoformat())
        except Exception: pass

async def main():
    db.init_db()
    asyncio.create_task(manual_check_worker())
    asyncio.create_task(sponsor_check_worker())
    asyncio.create_task(notifier_worker())
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
