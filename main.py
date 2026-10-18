# main.py
import asyncio
import logging
import aiohttp
import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder # <--- ВАЖНО: добавлено для админки
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

# Состояния для ввода данных
class WithdrawState(StatesGroup):
    waiting_amount = State()

class AdminStates(StatesGroup):
    waiting_sponsor_name = State()
    waiting_sponsor_link = State()
    waiting_sponsor_id = State()
    waiting_give_stars = State()
    waiting_broadcast = State()
    waiting_avatar = State()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def format_amount(amount):
    return f"{amount:.2f}".rstrip('0').rstrip('.') if amount % 1 else f"{amount:.0f}"

# ==========================================
# API СЕРВИСОВ
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
    builder.row(InlineKeyboardButton(text="🎁 Спонсоры (ОП)", callback_data="admin_sponsors"))
    builder.row(InlineKeyboardButton(text="💰 Заявки на вывод", callback_data="admin_withdraws"))
    builder.row(InlineKeyboardButton(text="⭐ Начислить звезды", callback_data="admin_give_stars"))
    builder.row(InlineKeyboardButton(text="🖼 Сменить аву", callback_data="admin_change_avatar"))
    
    await message.answer("👨‍💻 <b>Админ-панель</b>\nВыбери раздел:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_admin(callback.message, state)

@router.callback_query(F.data == "admin_sponsors")
async def admin_sponsors(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    sponsors = db.get_sponsors()
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_sponsor"))
    for sp in sponsors:
        builder.row(InlineKeyboardButton(text=f"❌ Удалить {sp['channel_name']}", callback_data=f"admin_del_sp_{sp['id']}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back"))
    
    text = "🎁 <b>Спонсоры (Обязательная подписка)</b>\n\n"
    if not sponsors: text += "Список пуст. Добавь первый канал."
    else:
        for sp in sponsors: text += f"├ {sp['channel_name']} ({sp['channel_id']})\n"
            
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data == "admin_add_sponsor")
async def admin_add_sponsor(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("Введи <b>название</b> канала:")
    await state.set_state(AdminStates.waiting_sponsor_name)

@router.message(AdminStates.waiting_sponsor_name)
async def process_sponsor_name(message: Message, state: FSMContext):
    await state.update_data(sp_name=message.text)
    await message.answer("Введи <b>ссылку</b> на канал:")
    await state.set_state(AdminStates.waiting_sponsor_link)

@router.message(AdminStates.waiting_sponsor_link)
async def process_sponsor_link(message: Message, state: FSMContext):
    await state.update_data(sp_link=message.text)
    await message.answer("Введи <b>ID канала</b> (например -100123456789):")
    await state.set_state(AdminStates.waiting_sponsor_id)

@router.message(AdminStates.waiting_sponsor_id)
async def process_sponsor_id(message: Message, state: FSMContext):
    data = await state.get_data()
    db.add_sponsor(data['sp_name'], data['sp_link'], message.text)
    await message.answer("✅ Канал добавлен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="К спонсорам", callback_data="admin_sponsors")]]))
    await state.clear()

@router.callback_query(F.data.startswith("admin_del_sp_"))
async def admin_del_sponsor(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    sp_id = int(callback.data.split("_")[3])
    db.delete_sponsor(sp_id)
    await callback.answer("Канал удален", show_alert=True)
    await admin_sponsors(callback)

@router.callback_query(F.data == "admin_give_stars")
async def admin_give_stars(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("Введи <b>ID юзера</b> и <b>сумму</b> через пробел:")
    await state.set_state(AdminStates.waiting_give_stars)

@router.message(AdminStates.waiting_give_stars)
async def process_give_stars(message: Message, state: FSMContext):
    try:
        uid, amount = map(float, message.text.split())
        db.add_balance(int(uid), amount, "admin_give")
        await message.answer(f"✅ Начислено {format_amount(amount)} ⭐ юзеру {int(uid)}")
        try: await bot.send_message(int(uid), f"🎁 Администратор начислил вам {format_amount(amount)} ⭐")
        except: pass
    except: await message.answer("Ошибка. Введи ID и сумму через пробел.")
    await state.clear()

@router.callback_query(F.data == "admin_change_avatar")
async def admin_change_avatar(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("Отправь мне фото, которое станет главным в боте:")
    await state.set_state(AdminStates.waiting_avatar)

@router.message(AdminStates.waiting_avatar, F.photo)
async def process_avatar(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    # В реальности сохраняем file_id в БД (таблица settings), здесь просто заглушка
    with db.get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('menu_avatar', ?)", (file_id,))
        conn.commit()
    await message.answer("✅ Ава главного меню обновлена!")
    await state.clear()

# ЗАЯВКИ НА ВЫВОД (АДМИНКА)
@router.callback_query(F.data == "admin_withdraws")
async def admin_withdraws(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    
    with db.get_conn() as conn:
        wds = conn.execute("SELECT * FROM withdrawals WHERE status = 'pending'").fetchall()
        
    if not wds:
        await callback.message.edit_text("Заявок нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]]))
        return
        
    wd = wds[0]
    text = f"💰 <b>Заявка #{wd['id']}</b>\n\nЮзер: <code>{wd['user_id']}</code>\nСумма: <b>{format_amount(wd['amount'])}</b> ⭐"
    
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

# ==========================================
# ХЕНДЛЕРЫ СТАРТА И ОП
# ==========================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    if not user:
        ref_id = None
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            ref_id = int(args[1])
            if ref_id == user_id: ref_id = None
        
        db.create_user(user_id, message.from_user.username, message.from_user.first_name, ref_id)
        if ref_id:
            db.add_ref(ref_id)
            try:
                ref_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
                await bot.send_message(ref_id, f'<tg-emoji emoji-id="5456140674028019486">⚡️</tg-emoji> <b>{ref_name}</b> присоединился по твоей ссылке!\n\nТы получишь <b>{format_amount(REF_BONUS)}</b> ⭐, как только он выполнит <b>{REF_TASKS_REQUIRED}</b> заданий')
            except: pass
    else:
        db.update_user_username(user_id, message.from_user.username, message.from_user.first_name)

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
    
    # Берем картинку из БД
    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'menu_avatar'").fetchone()
    
    if row:
        await message.answer_photo(photo=row['value'], caption=text, reply_markup=kb.main_menu_kb())
    else:
        await message.answer(text, reply_markup=kb.main_menu_kb())

@router.callback_query(F.data == "check_sub")
async def process_sub_check(callback: CallbackQuery):
    user_id = callback.from_user.id
    sponsors = db.get_sponsors()
    
    if not sponsors:
        await callback.message.delete()
        await send_main_menu(callback.message)
        return

    sp = sponsors[0]
    try:
        member = await bot.get_chat_member(chat_id=sp['channel_id'], user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            await callback.message.delete()
            await send_main_menu(callback.message)
            await callback.answer()
        else:
            await callback.answer("Вы не подписались на канал!", show_alert=True)
    except Exception as e:
        await callback.answer("Ошибка проверки. Бот админ в канале?", show_alert=True)

# ==========================================
# МЕНЮ НАВИГАЦИЯ
# ==========================================
@router.callback_query(F.data == "menu_back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await send_main_menu(callback.message)
    await callback.answer()

# ==========================================
# РЕФЕРАЛЫ
# ==========================================
@router.callback_query(F.data == "menu_refs")
async def show_refs(callback: CallbackQuery):
    user_id = callback.from_user.id
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
        ref_bonus=format_amount(REF_BONUS),
        ref_tasks_required=REF_TASKS_REQUIRED,
        ref_link=ref_link,
        total_refs=user['total_refs'],
        confirmed_refs=user['confirmed_refs'],
        ref_list=ref_list_text,
        balance=format_amount(user['balance'])
    )
    await callback.message.edit_text(text, reply_markup=kb.back_kb())

# ==========================================
# ПРОФИЛЬ
# ==========================================
@router.callback_query(F.data == "menu_profile")
async def show_profile(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    name = f"@{user['username']}" if user['username'] else user['first_name']
    text = DEFAULTS["profile_text"].format(
        username=name,
        total_refs=user['total_refs'],
        total_earned=format_amount(user['total_earned']),
        balance=format_amount(user['balance']),
        user_id=user['user_id'],
        tasks_completed=user['tasks_completed']
    )
    await callback.message.edit_text(text, reply_markup=kb.back_kb())

# ==========================================
# ВЫВОД
# ==========================================
@router.callback_query(F.data == "menu_withdraw")
async def show_withdraw(callback: CallbackQuery, state: FSMContext):
    user = db.get_user(callback.from_user.id)
    amounts_str = ", ".join(map(str, WITHDRAW_AMOUNTS))
    text = DEFAULTS["withdraw_text"].format(
        balance=format_amount(user['balance']),
        amounts=amounts_str
    )
    await callback.message.edit_text(text, reply_markup=kb.withdraw_kb())
    await state.set_state(WithdrawState.waiting_amount)

@router.callback_query(WithdrawState.waiting_amount, F.data.startswith("wd_"))
async def process_withdraw_button(callback: CallbackQuery, state: FSMContext):
    amount = float(callback.data.split("_")[1])
    await process_withdraw_request(callback.message, callback.from_user.id, amount)
    await callback.answer()
    await state.clear()

@router.message(WithdrawState.waiting_amount)
async def process_withdraw_text(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount not in WITHDRAW_AMOUNTS:
            await message.answer(f"Доступные суммы: {', '.join(map(str, WITHDRAW_AMOUNTS))}")
            return
        await process_withdraw_request(message, message.from_user.id, amount)
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите число.")

async def process_withdraw_request(message: Message, user_id: int, amount: float):
    user = db.get_user(user_id)
    if user['balance'] < amount:
        await message.answer(f"Не хватает звёзд. Баланс: {format_amount(user['balance'])} ⭐")
        return
    if user['confirmed_refs'] < WITHDRAW_FRIENDS_REQUIRED:
        need = WITHDRAW_FRIENDS_REQUIRED - user['confirmed_refs']
        await message.answer(f"⚠️ <b>Недостаточно друзей для вывода!</b>\n\nДля вывода нужно пригласить еще <b>{need}</b> друзей.\nСейчас у вас: <b>{user['confirmed_refs']}</b> из <b>{WITHDRAW_FRIENDS_REQUIRED}</b>.")
        return
        
    wd_id = db.create_withdraw(user_id, amount)
    db.remove_balance(user_id, amount)
    await message.answer(f"✅ Заявка <b>#{wd_id}</b> на <b>{format_amount(amount)}</b> ⭐ создана.\nСрок вывода: 5 минут — 24 часа.", reply_markup=kb.back_kb())
    
    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, f"💰 Новая заявка #{wd_id} от @{user['username']} на {format_amount(amount)} ⭐")
        except: pass

# ==========================================
# ИНСТРУКЦИЯ И СТАТИСТИКА
# ==========================================
@router.callback_query(F.data == "menu_instruction")
async def show_instruction(callback: CallbackQuery):
    await callback.message.edit_text(DEFAULTS["instruction_text"], reply_markup=kb.back_kb())

@router.callback_query(F.data == "menu_stats")
async def show_stats(callback: CallbackQuery):
    text = DEFAULTS["stats_text"].format(
        total_users=db.get_total_users(),
        total_withdrawn=format_amount(db.get_total_withdrawn())
    )
    await callback.message.edit_text(text, reply_markup=kb.stats_kb())

@router.callback_query(F.data.startswith("top_"))
async def show_top(callback: CallbackQuery):
    top_type = callback.data.split("_")[1]
    await callback.message.edit_text("Топ в разработке...", reply_markup=kb.back_kb("menu_stats"))

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
            await message.answer("😔 На данный момент нет доступных заданий. Попробуйте позже.", reply_markup=kb.back_kb())
            return
            
        # Проверка на дубликаты
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
        await send_next_task(callback.message, user_id)
        
        user = db.get_user(user_id)
        if user['referrer_id'] and not user['ref_bonus_paid']:
            if user['tasks_completed'] >= REF_TASKS_REQUIRED:
                db.confirm_ref(user['referrer_id'], REF_BONUS, user['tasks_completed'])
                try: await bot.send_message(user['referrer_id'], f'<tg-emoji emoji-id="5469641199348363998">⭐</tg-emoji> Твой реферал <b>@{user["username"]}</b> выполнил <b>{REF_TASKS_REQUIRED}</b> заданий: <b>+{format_amount(REF_BONUS)} ⭐</b>')
                except: pass
    else:
        await callback.message.edit_text("❌ Задание не выполнено. Попробуйте снова.", reply_markup=kb.task_kb(task["link"]))
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
# ЗАПУСК
# ==========================================
async def main():
    db.init_db()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
