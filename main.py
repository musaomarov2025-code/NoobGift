# main.py
import asyncio
import logging
import aiohttp
import os
import random
import string
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import (
    BOT_TOKEN, ADMIN_IDS, DEFAULTS, PIARFLOW_API_KEY, TGRASS_API_KEY, 
    TRAFSLY_API_KEY, TASK_REWARD, REF_BONUS, REF_TASKS_REQUIRED, 
    WITHDRAW_FRIENDS_REQUIRED, WITHDRAW_AMOUNTS
)
import database as db
import keyboards as kb

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ==========================================
# СОСТОЯНИЯ (FSM)
# ==========================================
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

def format_amount(amount):
    return f"{amount:.2f}".rstrip('0').rstrip('.') if amount % 1 else f"{amount:.0f}"

# ==========================================
# API СЕРВИСОВ (ЗАГЛУШКИ ДЛЯ ПРИМЕРА)
# ==========================================
async def get_task_from_piarflow(user_id):
    url = "https://piarflow.com/v1/sponsors"
    headers = {"Authorization": f"Bearer {PIARFLOW_API_KEY}"}
    payload = {"user_id": user_id, "chat_id": user_id, "max_sponsors": 1}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sponsors = data.get("sponsors", [])
                    if sponsors:
                        return {"service": "piarflow", "task_id": sponsors[0]["link"], "link": sponsors[0]["link"]}
        except: pass
    return None

async def get_task_from_tgrass(user_id):
    url = "https://tgrass.space/tasks"
    headers = {"Auth": TGRASS_API_KEY}
    payload = {"tg_user_id": user_id, "is_premium": False, "lang": "ru"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    offers = data.get("offers", [])
                    if offers and data.get("status") == "not_ok":
                        return {"service": "tgrass", "task_id": str(offers[0]["offer_id"]), "link": offers[0]["link"]}
        except: pass
    return None

async def get_task_from_trafsly(user_id):
    url = "https://api.trafsly.com/api/v1/get-sponsors"
    headers = {"Auth": TRAFSLY_API_KEY}
    payload = {"user_id": user_id}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    sponsors = data.get("sponsors", [])
                    if sponsors and data.get("status") == "warning":
                        return {"service": "trafsly", "task_id": str(sponsors[0]["ads_id"]), "link": sponsors[0]["link"]}
        except: pass
    return None

async def fetch_new_task(user_id):
    task = await get_task_from_piarflow(user_id)
    if not task: task = await get_task_from_tgrass(user_id)
    if not task: task = await get_task_from_trafsly(user_id)
    return task

async def check_task_status(service, user_id, task_id):
    if service == "piarflow":
        url = "https://piarflow.com/v1/sponsors/check"
        headers = {"Authorization": f"Bearer {PIARFLOW_API_KEY}"}
        payload = {"user_id": user_id, "links": [task_id]}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("sponsors", [{}])[0].get("status") in ["subscribed", "not_counted"]
    elif service == "tgrass":
        url = "https://tgrass.space/check"
        headers = {"Auth": TGRASS_API_KEY}
        payload = {"tg_user_id": user_id, "offer_id": int(task_id)}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("status") == "subscribed"
    elif service == "trafsly":
        url = "https://api.trafsly.com/api/v1/confirm-subscription"
        headers = {"Auth": TRAFSLY_API_KEY}
        payload = {"user_id": user_id, "ads_id": task_id}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("subscribed") is True
    return False

# ==========================================
# АДМИН ПАНЕЛЬ
# ==========================================
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id not in ADMIN_IDS: return
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats_main"))
    builder.row(
        InlineKeyboardButton(text="🎁 Спонсоры (ОП)", callback_data="admin_sponsors"),
        InlineKeyboardButton(text="💰 Заявки на вывод", callback_data="admin_withdraws")
    )
    builder.row(
        InlineKeyboardButton(text="🎫 Промокоды", callback_data="admin_promo"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="👤 Поиск юзера", callback_data="admin_find_user")
    )
    builder.row(
        InlineKeyboardButton(text="🖼 Сменить аву", callback_data="admin_change_avatar"),
        InlineKeyboardButton(text="💾 Бэкап", callback_data="admin_backup")
    )
    
    await message.answer("👨‍💻 <b>Админ-панель</b>\nВыбери раздел:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_admin(callback.message, state)
    await callback.answer()

# --- 1. СТАТИСТИКА БОТА ---
@router.callback_query(F.data == "admin_stats_main")
async def admin_stats(callback: CallbackQuery):
    total_users = db.get_total_users()
    new_today = db.get_new_users_today()
    total_balance = db.get_total_balance()
    total_withdrawn = db.get_total_withdrawn()
    tasks_done = db.get_total_tasks_done()
    
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего юзеров: <b>{total_users}</b>\n"
        f"🆕 Новых за сегодня: <b>{new_today}</b>\n"
        f"💰 Общий баланс: <b>{format_amount(total_balance)}</b> ⭐\n"
        f"💸 Всего выведено: <b>{format_amount(total_withdrawn)}</b> ⭐\n"
        f"✅ Заданий выполнено: <b>{tasks_done}</b>"
    )
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]]))

# --- 2. ПРОМОКОДЫ ---
@router.callback_query(F.data == "admin_promo")
async def admin_promo(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать чек", callback_data="admin_create_promo"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await callback.message.edit_text("🎫 <b>Управление промокодами</b>\n\nЗдесь ты можешь создавать чеки на звезды.", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_create_promo")
async def admin_create_promo(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи <b>сумму</b> (одно число) или <b>диапазон</b> через дефис (например, 4-50):")
    await state.set_state(AdminStates.waiting_promo_sum)

@router.message(AdminStates.waiting_promo_sum)
async def process_promo_sum(message: Message, state: FSMContext):
    try:
        if "-" in message.text:
            amin, amax = map(float, message.text.split("-"))
        else:
            amin = amax = float(message.text)
        await state.update_data(amin=amin, amax=amax)
        await message.answer("Сколько раз можно активировать чек?")
        await state.set_state(AdminStates.waiting_promo_act)
    except:
        await message.answer("Ошибка. Введи число или диапазон (4-50).")

@router.message(AdminStates.waiting_promo_act)
async def process_promo_act(message: Message, state: FSMContext):
    try:
        max_act = int(message.text)
        data = await state.get_data()
        
        # Генерируем код
        code = "check_" + ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        db.create_promo(code, data['amin'], data['amax'], max_act, False)
        
        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={code}"
        
        await message.answer(f"✅ Чек создан!\nСсылка: {link}\nСумма: {data['amin']}-{data['amax']} ⭐\nАктиваций: {max_act}")
        await state.clear()
    except:
        await message.answer("Ошибка. Введи число.")

# --- 3. НАСТРОЙКИ ---
@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ Награда за задание", callback_data="set_task_reward"))
    builder.row(InlineKeyboardButton(text="👥 Бонус за реферала", callback_data="set_ref_bonus"))
    builder.row(InlineKeyboardButton(text="🤝 Друзей для вывода", callback_data="set_withdraw_friends"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await callback.message.edit_text("⚙️ <b>Настройки экономики</b>\nВыбери, что изменить:", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("set_"))
async def setting_change(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split("_")[1] + "_" + callback.data.split("_")[2]
    await state.update_data(set_key=key)
    await callback.message.edit_text("Введи новое значение:")
    await state.set_state(AdminStates.waiting_setting_value)

@router.message(AdminStates.waiting_setting_value)
async def process_setting_value(message: Message, state: FSMContext):
    data = await state.get_data()
    db.set_setting(data['set_key'], message.text)
    await message.answer("✅ Настройка сохранена!")
    await state.clear()

# --- 4. ПОИСК ЮЗЕРА ---
@router.callback_query(F.data == "admin_find_user")
async def admin_find_user(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введи ID юзера для просмотра информации:")
    await state.set_state(AdminStates.waiting_user_info)

@router.message(AdminStates.waiting_user_info)
async def process_user_info(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        u = db.get_user(uid)
        if not u:
            await message.answer("Юзер не найден.")
            return
            
        refs = db.get_user_referrals(uid)
        wds = db.get_user_withdraws(uid)
        
        text = (
            f"👤 <b>Инфо о юзере</b> {uid}\n\n"
            f"Ник: @{u['username']} ({u['first_name']})\n"
            f"Баланс: {format_amount(u['balance'])} ⭐\n"
            f"Всего заработано: {format_amount(u['total_earned'])} ⭐\n"
            f"Заданий выполнено: {u['tasks_completed']}\n"
            f"Друзей: {u['total_refs']} (подтверждено: {u['confirmed_refs']})\n"
            f"Заявок на вывод: {len(wds)}\n"
            f"Регистрация: {u['reg_date']}"
        )
        await message.answer(text)
    except:
        await message.answer("Ошибка ID.")
    await state.clear()

# --- 5. ВЫВОД С ПРОВЕРКОЙ ---
@router.callback_query(F.data == "admin_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    with db.get_conn() as conn:
        wds = conn.execute("SELECT * FROM withdrawals WHERE status = 'pending'").fetchall()
    if not wds:
        await callback.message.edit_text("Заявок нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]]))
        return
    
    wd = wds[0]
    u = db.get_user(wd['user_id'])
    
    text = (
        f"💰 <b>Заявка #{wd['id']}</b>\n\n"
        f"Юзер: @{u['username']} (ID: {u['user_id']})\n"
        f"Сумма: <b>{format_amount(wd['amount'])}</b> ⭐\n\n"
        f"📊 <b>Проверка:</b>\n"
        f"├ Друзей: {u['total_refs']} (подтверждено: {u['confirmed_refs']})\n"
        f"├ Заданий сделал: {u['tasks_completed']}\n"
        f"└ Дата заявки: {wd['created_at']}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Выплачено", callback_data=f"admin_pay_{wd['id']}", style="success"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_rej_{wd['id']}", style="danger")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("admin_pay_"))
async def admin_pay(callback: CallbackQuery):
    wd_id = int(callback.data.split("_")[2])
    db.update_withdraw_status(wd_id, 'paid')
    wd = db.get_withdraw(wd_id)
    try: await bot.send_message(wd['user_id'], f"✅ Заявка <b>#{wd_id}</b> на <b>{format_amount(wd['amount'])}</b> ⭐ выплачена!")
    except: pass
    await callback.answer("Выплачено!", show_alert=True)
    await admin_withdraws(callback)

@router.callback_query(F.data.startswith("admin_rej_"))
async def admin_rej(callback: CallbackQuery):
    wd_id = int(callback.data.split("_")[2])
    db.update_withdraw_status(wd_id, 'rejected')
    wd = db.get_withdraw(wd_id)
    db.add_balance(wd['user_id'], wd['amount'], "refund")
    await callback.answer("Отклонено, баланс возвращен.", show_alert=True)
    await admin_withdraws(callback)

# --- 6. ОСТАЛЬНОЕ (АВА, РАССЫЛКА, БЭКАП) ---
@router.callback_query(F.data == "admin_change_avatar")
async def admin_change_avatar(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправь мне фото для главного меню:")
    await state.set_state(AdminStates.waiting_avatar)

@router.message(AdminStates.waiting_avatar, F.photo)
async def process_avatar(message: Message, state: FSMContext):
    db.set_setting("menu_avatar", message.photo[-1].file_id)
    await message.answer("✅ Ава обновлена!")
    await state.clear()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправь текст для рассылки:")
    await state.set_state(AdminStates.waiting_broadcast)

@router.message(AdminStates.waiting_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    with db.get_conn() as conn:
        users = conn.execute("SELECT user_id FROM users").fetchall()
    await message.answer(f"Начинаю рассылку для {len(users)}...")
    success = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.html_text)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Отправлено: {success}")
    await state.clear()

@router.callback_query(F.data == "admin_backup")
async def admin_backup(callback: CallbackQuery):
    try:
        doc = FSInputFile(db.get_db_path())
        await callback.message.answer_document(doc, caption="💾 Бэкап базы")
    except Exception as e:
        await callback.message.answer(f"Ошибка: {e}")
    await callback.answer()

# ==========================================
# ХЕНДЛЕРЫ СТАРТА (С ФОТО)
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    args = message.text.split()
    param = args[1] if len(args) > 1 else None
    
    # Проверка промокода
    if param and param.startswith("check_"):
        promo = db.get_promo(param)
        if not promo or promo['current_activations'] >= promo['max_activations']:
            await message.answer("⚠️ Чек не найден или больше не активен.")
            return
        if db.check_promo_activation(param, user_id):
            await message.answer("⚠️ Вы уже активировали этот чек.")
            return
        
        # Активация
        amount = round(random.uniform(promo['amount_min'], promo['amount_max']), 2)
        db.activate_promo(param, user_id, amount)
        await message.answer(f"🎉 Вы активировали чек и получили <b>{format_amount(amount)} ⭐</b>!")
        return

    if not user:
        ref_id = None
        ad_code = None
        if param:
            if param.isdigit():
                ref_id = int(param)
                if ref_id == user_id: ref_id = None
            else:
                ad_code = param
        db.create_user(user_id, message.from_user.username, message.from_user.first_name, ref_id, ad_code)
    
    sponsors = db.get_sponsors()
    if sponsors:
        sp = sponsors[0]
        await message.answer(
            DEFAULTS["sub_text"].format(channel_name=sp['channel_name']),
            reply_markup=kb.sub_check_kb(sp['channel_link'], sp['channel_name'])
        )
        return

    await send_main_menu(message)

async def send_main_menu(message: Message):
    text = DEFAULTS["menu_text"].format(ref_bonus=format_amount(REF_BONUS))
    avatar = db.get_setting("menu_avatar")
    
    if avatar:
        await message.answer_photo(photo=avatar, caption=text, reply_markup=kb.main_menu_kb())
    else:
        await message.answer(text, reply_markup=kb.main_menu_kb())

@router.callback_query(F.data == "check_sub")
async def process_sub_check(callback: CallbackQuery):
    sponsors = db.get_sponsors()
    if not sponsors:
        await callback.message.delete()
        await send_main_menu(callback.message)
        return
    sp = sponsors[0]
    try:
        member = await bot.get_chat_member(chat_id=sp['channel_id'], user_id=callback.from_user.id)
        if member.status in ['member', 'administrator', 'creator']:
            await callback.message.delete()
            await send_main_menu(callback.message)
            await callback.answer()
        else:
            await callback.answer("Вы не подписались на канал!", show_alert=True)
    except:
        await callback.answer("Ошибка проверки. Бот админ в канале?", show_alert=True)

# ==========================================
# НАВИГАЦИЯ (ИСПРАВЛЕНО!)
# ==========================================
@router.callback_query(F.data == "menu_back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await callback.message.delete()
    except: pass
    await send_main_menu(callback.message)
    await callback.answer()

# ==========================================
# РЕФЕРАЛЫ, ПРОФИЛЬ, ВЫВОД, СТАТИСТИКА (ТЕКСТ)
# ==========================================
@router.callback_query(F.data == "menu_refs")
async def show_refs(callback: CallbackQuery):
    # ... (код рефов оставляем как был, только edit_text меняем на delete+answer для безопасности)
    try: await callback.message.delete()
    except: pass
    # Вставляем логику отправки рефов
    await send_refs_menu(callback.message, callback.from_user.id)

async def send_refs_menu(message: Message, user_id):
    user = db.get_user(user_id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    with db.get_conn() as conn:
        refs = conn.execute("SELECT * FROM users WHERE referrer_id = ?", (user_id,)).fetchall()
    ref_list_text = ""
    for r in refs:
        name = f"@{r['username']}" if r['username'] else f"id {r['user_id']}"
        status = f"{r['tasks_completed']} заданий"
        if r['tasks_completed'] < REF_TASKS_REQUIRED:
            status = "проходит вход" if r['tasks_completed'] == 0 else f"{r['tasks_completed']} заданий"
        ref_list_text += f"├ {name} — {status}\n"
    if not ref_list_text: ref_list_text = "├ Пока никого нет\n"
    text = DEFAULTS["ref_text"].format(
        ref_bonus=format_amount(REF_BONUS), ref_tasks_required=REF_TASKS_REQUIRED,
        ref_link=ref_link, total_refs=user['total_refs'], confirmed_refs=user['confirmed_refs'],
        ref_list=ref_list_text, balance=format_amount(user['balance'])
    )
    await message.answer(text, reply_markup=kb.back_kb())

@router.callback_query(F.data == "menu_profile")
async def show_profile(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    user = db.get_user(callback.from_user.id)
    name = f"@{user['username']}" if user['username'] else user['first_name']
    text = DEFAULTS["profile_text"].format(
        username=name, total_refs=user['total_refs'], total_earned=format_amount(user['total_earned']),
        balance=format_amount(user['balance']), user_id=user['user_id'], tasks_completed=user['tasks_completed']
    )
    await callback.message.answer(text, reply_markup=kb.back_kb())

@router.callback_query(F.data == "menu_withdraw")
async def show_withdraw(callback: CallbackQuery, state: FSMContext):
    try: await callback.message.delete()
    except: pass
    user = db.get_user(callback.from_user.id)
    amounts_str = ", ".join(map(str, WITHDRAW_AMOUNTS))
    text = DEFAULTS["withdraw_text"].format(balance=format_amount(user['balance']), amounts=amounts_str)
    await callback.message.answer(text, reply_markup=kb.withdraw_kb())
    await state.set_state(WithdrawState.waiting_amount)

@router.callback_query(F.data == "menu_instruction")
async def show_instruction(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    await callback.message.answer(DEFAULTS["instruction_text"], reply_markup=kb.back_kb())

@router.callback_query(F.data == "menu_stats")
async def show_stats(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    text = DEFAULTS["stats_text"].format(total_users=db.get_total_users(), total_withdrawn=format_amount(db.get_total_withdrawn()))
    await callback.message.answer(text, reply_markup=kb.stats_kb())

# ==========================================
# ЗАДАНИЯ
# ==========================================
@router.callback_query(F.data == "menu_earn")
async def show_tasks(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    await send_next_task(callback.message, callback.from_user.id)
    await callback.answer()

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
        db.save_task(user_id, new_task["service"], new_task["task_id"], new_task["link"], TASK_REWARD)
        task = db.get_pending_task(user_id)
    if not task:
        await message.answer("😔 Нет доступных заданий.", reply_markup=kb.back_kb())
        return
    text = DEFAULTS["task_text"].format(reward=format_amount(TASK_REWARD))
    await message.answer(text, reply_markup=kb.task_kb(task["link"]))

@router.callback_query(F.data == "check_task")
async def check_task(callback: CallbackQuery):
    user_id = callback.from_user.id
    task = db.get_pending_task(user_id)
    if not task:
        await callback.answer("Задание не найдено.", show_alert=True)
        return
    await callback.message.edit_text("⏳ Проверяем задание...")
    is_done = await check_task_status(task['service'], user_id, task['task_id'])
    if is_done:
        db.add_balance(user_id, TASK_REWARD, "task")
        db.mark_task_completed(user_id)
        db.mark_task_status(task['id'], 'done')
        await callback.message.edit_text(f"✅ Задание выполнено! Начислено: {format_amount(TASK_REWARD)} ⭐")
        await asyncio.sleep(1.5)
        await callback.message.delete()
        await send_next_task(callback.message, user_id)
    else:
        await callback.message.edit_text("❌ Задание не выполнено.", reply_markup=kb.task_kb(task["link"]))
    await callback.answer()

@router.callback_query(F.data == "skip_task")
async def skip_task(callback: CallbackQuery):
    user_id = callback.from_user.id
    task = db.get_pending_task(user_id)
    if task:
        db.mark_task_status(task['id'], 'skipped')
    await callback.answer("Задание пропущено", show_alert=True)
    try: await callback.message.delete()
    except: pass
    await send_next_task(callback.message, user_id)

# ==========================================
# ВЫВОД
# ==========================================
@router.callback_query(WithdrawState.waiting_amount, F.data.startswith("wd_"))
async def process_withdraw_button(callback: CallbackQuery, state: FSMContext):
    amount = float(callback.data.split("_")[1])
    await process_withdraw_request(callback.message, callback.from_user.id, amount)
    await callback.answer()
    await state.clear()

async def process_withdraw_request(message: Message, user_id: int, amount: float):
    user = db.get_user(user_id)
    if user['balance'] < amount:
        await message.answer(f"Не хватает звёзд. Баланс: {format_amount(user['balance'])} ⭐")
        return
    if user['confirmed_refs'] < WITHDRAW_FRIENDS_REQUIRED:
        need = WITHDRAW_FRIENDS_REQUIRED - user['confirmed_refs']
        await message.answer(f"⚠️ <b>Недостаточно друзей для вывода!</b>\n\nНужно: <b>{need}</b>.\nСейчас: <b>{user['confirmed_refs']}</b>.")
        return
    wd_id = db.create_withdraw(user_id, amount)
    db.remove_balance(user_id, amount)
    await message.answer(f"✅ Заявка <b>#{wd_id}</b> на <b>{format_amount(amount)}</b> ⭐ создана.", reply_markup=kb.back_kb())
    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, f"💰 Новая заявка #{wd_id}")
        except: pass

# ==========================================
# ЗАПУСК И АВТОБЭКАП (В ФОНЕ)
# ==========================================
async def auto_backup_worker():
    # Фоновый воркер для бэкапа (простейший пример, лучше использовать aioschedule)
    while True:
        now = datetime.datetime.now()
        # 8:00 и 20:00
        if now.hour in [8, 20] and now.minute == 0:
            for admin in ADMIN_IDS:
                try:
                    doc = FSInputFile(db.get_db_path())
                    await bot.send_document(admin, doc, caption=f"💾 Автобэкап за {now.strftime('%d.%m.%Y %H:%M')}")
                except: pass
            await asyncio.sleep(60) # Ждем минуту, чтобы не спамить
        await asyncio.sleep(30)

async def main():
    db.init_db()
    asyncio.create_task(auto_backup_worker()) # Запуск бэкапа
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import datetime
    asyncio.run(main())
