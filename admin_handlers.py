import aiosqlite
import json
import os
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from main import ADMIN_ID, DB_PATH, bot
from database import (
    get_user, set_user_banned, get_setting, set_setting,
    get_services, update_service_key, toggle_service, swap_service_priority,
    get_withdrawal, process_withdrawal, add_promo, get_all_shows, delete_promo,
    add_traffic_ad, get_traffic_ad, get_traffic_stats
)
from keyboards import (
    admin_main_kb, admin_user_kb, admin_withdraw_kb, 
    admin_services_kb, admin_settings_kb, admin_back_kb,
    admin_broadcast_kb, admin_promos_kb, admin_ads_kb,
    AdminStates
)

admin_router = Router()

# Фильтр для админа
admin_router.message.filter(F.from_user.id == ADMIN_ID)
admin_router.callback_query.filter(F.from_user.id == ADMIN_ID)

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())

@admin_router.callback_query(F.data == "adm_back")
async def adm_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_main_kb())
    await callback.answer()

# ================= СТАТИСТИКА =================
@admin_router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        async with db.execute("SELECT COUNT(*) as users, SUM(total_earned) as earned, SUM(tasks_done) as tasks FROM users") as c:
            gen = await c.fetchone()
            
        async with db.execute("""
            SELECT service, COUNT(*) as cnt FROM task_completions 
            GROUP BY service ORDER BY cnt DESC LIMIT 6
        """) as c:
            top_services = await c.fetchall()
            
        async with db.execute("SELECT username, tasks_done FROM users ORDER BY tasks_done DESC LIMIT 1") as c:
            top_tasks = await c.fetchone()
            
        async with db.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 1") as c:
            top_bal = await c.fetchone()

    text = (
        f"📊 <b>Полная статистика</b>\n\n"
        f"👥 Всего юзеров: {gen['users'] or 0}\n"
        f"💰 Всего заработано: {gen['earned'] or 0:.2f} ⭐\n"
        f"✅ Выполнено заданий: {gen['tasks'] or 0}\n\n"
        f"🔥 <b>Топ сервисов по заданиям:</b>\n"
    )
    
    for i, srv in enumerate(top_services, 1):
        text += f"{i}. {srv['service']}: {srv['cnt']} шт.\n"
        
    if top_tasks:
        text += f"\n🏆 <b>Топ по заданиям:</b>\n@{top_tasks['username']} ({top_tasks['tasks_done']} шт.)\n"
    if top_bal:
        text += f"\n💎 <b>Топ по балансу:</b>\n@{top_bal['username']} ({top_bal['balance']:.2f} ⭐)"

    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()

# ================= ЮЗЕР =================
@admin_router.callback_query(F.data == "adm_user")
async def adm_user_search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_search)
    await callback.message.edit_text("👤 Введите ID или @username юзера:", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_user_search)
async def adm_user_search(message: Message, state: FSMContext):
    query = message.text.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if query.startswith("@"):
            async with db.execute("SELECT * FROM users WHERE username = ?", (query[1:],)) as c:
                user = await c.fetchone()
        elif query.isdigit():
            async with db.execute("SELECT * FROM users WHERE id = ?", (int(query),)) as c:
                user = await c.fetchone()
        else:
            await message.answer("Неверный формат. Введите ID или @username.")
            return

    if not user:
        await message.answer("❌ Юзер не найден.")
        return

    text = (
        f"👤 <b>Инфо о юзере</b>\n\n"
        f"🆔 ID: <code>{user['id']}</code>\n"
        f"🔗 Юз: @{user['username']}\n"
        f"💰 Баланс: {user['balance']:.2f} ⭐\n"
        f"📈 Всего заработал: {user['total_earned']:.2f} ⭐\n"
        f"✅ Заданий: {user['tasks_done']}\n"
        f"👥 Рефералов: {user['ref_count']}\n"
        f"❌ Бан: {'Да' if user['banned'] else 'Нет'}\n"
        f"📅 Регистрация: {user['created_at']}\n"
    )
    await state.clear()
    await message.answer(text, reply_markup=admin_user_kb(user['id'], user['banned']))

@admin_router.callback_query(F.data.startswith("adm_usr_ban_"))
async def adm_user_ban(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[3])
    user = await get_user(user_id)
    new_ban = 0 if user['banned'] else 1
    await set_user_banned(user_id, new_ban)
    
    status = "забанен" if new_ban else "разбанен"
    await callback.answer(f"Юзер {status}!")
    await callback.message.edit_reply_markup(reply_markup=admin_user_kb(user_id, new_ban))

@admin_router.callback_query(F.data.startswith("adm_usr_bal_"))
async def adm_user_bal_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[3])
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.waiting_for_new_balance)
    await callback.message.edit_text("💰 Введите новый баланс (например, 50.5):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_new_balance)
async def adm_user_bal_set(message: Message, state: FSMContext):
    try:
        new_bal = float(message.text.replace(",", "."))
        data = await state.get_data()
        user_id = data['target_user_id']
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET balance = ? WHERE id = ?", (new_bal, user_id))
            await db.commit()
            
        await state.clear()
        await message.answer(f"✅ Баланс юзера <code>{user_id}</code> изменен на {new_bal:.2f} ⭐", reply_markup=admin_main_kb())
    except ValueError:
        await message.answer("❌ Ошибка. Введите число.")

# ================= ЗАЯВКИ НА ВЫВОД =================
@admin_router.callback_query(F.data == "adm_withdrawals")
async def adm_wd_list(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY id ASC LIMIT 1") as c:
            wd = await c.fetchone()
            
    if not wd:
        await callback.message.edit_text("✅ Нет активных заявок на вывод.", reply_markup=admin_back_kb())
        await callback.answer()
        return

    user = await get_user(wd['user_id'])
    ref_user = await get_user(user['ref_by']) if user['ref_by'] else None
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT SUM(tasks_done) FROM users WHERE ref_by = ?", (user['id'],)) as c:
            ref_tasks = (await c.fetchone())[0] or 0

    text = (
        f"💸 <b>Заявка #{wd['id']}</b>\n\n"
        f"👤 Юзер: <code>{user['id']}</code> (@{user['username']})\n"
        f"💰 Сумма: {wd['amount']} ⭐\n"
        f"📈 Всего заработал: {user['total_earned']:.2f} ⭐\n"
        f"✅ Выполнил заданий: {user['tasks_done']}\n\n"
        f"👥 <b>Реферер:</b> "
    )
    if ref_user:
        text += f"<code>{ref_user['id']}</code> (@{ref_user['username']})\n"
        text += f"📊 Заданий от его рефов: {ref_tasks}\n"
    else:
        text += "Нет\n"
        
    text += f"\n📅 Дата: {wd['created_at']}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_wd_ok_{wd['id']}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_wd_no_{wd['id']}")],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="adm_wd_skip")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@admin_router.callback_query(F.data == "adm_wd_skip")
async def adm_wd_skip(callback: CallbackQuery):
    await adm_wd_list(callback)

@admin_router.callback_query(F.data.startswith("adm_wd_ok_"))
async def adm_wd_ok(callback: CallbackQuery):
    wd_id = int(callback.data.split("_")[3])
    wd = await get_withdrawal(wd_id)
    await process_withdrawal(wd_id, 'approved')
    
    try:
        await bot.send_message(wd['user_id'], f"✅ Заявка #{wd_id} на {wd['amount']} ⭐ выплачена!")
    except: pass
    
    await callback.answer("Заявка одобрена!")
    await adm_wd_list(callback)

@admin_router.callback_query(F.data.startswith("adm_wd_no_"))
async def adm_wd_no(callback: CallbackQuery):
    wd_id = int(callback.data.split("_")[3])
    wd = await get_withdrawal(wd_id)
    await process_withdrawal(wd_id, 'rejected')
    
    try:
        await bot.send_message(wd['user_id'], f"❌ Заявка #{wd_id} отклонена. Звёзды возвращены на баланс.")
    except: pass
    
    await callback.answer("Заявка отклонена!")
    await adm_wd_list(callback)

# ================= СЕРВИСЫ =================
def get_services_admin_kb(services):
    kb = []
    for s in services:
        status = "🟢" if s['is_active'] else "🔴"
        kb.append([
            InlineKeyboardButton(text=f"{status} {s['name']}", callback_data=f"adm_srv_toggle_{s['id']}"),
            InlineKeyboardButton(text="🔑", callback_data=f"adm_srv_key_{s['id']}"),
            InlineKeyboardButton(text="⬆️", callback_data=f"adm_srv_up_{s['id']}"),
            InlineKeyboardButton(text="⬇️", callback_data=f"adm_srv_down_{s['id']}")
        ])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@admin_router.callback_query(F.data == "adm_services")
async def adm_services(callback: CallbackQuery):
    services = await get_services()
    await callback.message.edit_text("⚙️ <b>Управление сервисами:</b>\n🟢 - вкл, 🔴 - выкл. 🔑 - ключ, ⬆️⬇️ - приоритет.", reply_markup=get_services_admin_kb(services))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("adm_srv_toggle_"))
async def adm_srv_toggle(callback: CallbackQuery):
    srv_id = int(callback.data.split("_")[3])
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_active FROM services WHERE id = ?", (srv_id,)) as c:
            is_act = (await c.fetchone())[0]
    await toggle_service(srv_id, 0 if is_act else 1)
    services = await get_services()
    await callback.message.edit_reply_markup(reply_markup=get_services_admin_kb(services))
    await callback.answer("Статус изменен")

@admin_router.callback_query(F.data.startswith("adm_srv_key_"))
async def adm_srv_key_start(callback: CallbackQuery, state: FSMContext):
    srv_id = int(callback.data.split("_")[3])
    await state.update_data(srv_id=srv_id)
    await state.set_state(AdminStates.waiting_for_service_key)
    await callback.message.edit_text("🔑 Отправь новый API-ключ для этого сервиса:", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_service_key)
async def adm_srv_key_set(message: Message, state: FSMContext):
    data = await state.get_data()
    await update_service_key(data['srv_id'], message.text.strip())
    await state.clear()
    services = await get_services()
    await message.answer("✅ Ключ обновлен!", reply_markup=get_services_admin_kb(services))

@admin_router.callback_query(F.data.startswith("adm_srv_up_") | F.data.startswith("adm_srv_down_"))
async def adm_srv_priority(callback: CallbackQuery):
    action = callback.data.split("_")[2]
    srv_id = int(callback.data.split("_")[3])
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, priority FROM services ORDER BY priority ASC") as c:
            srv_list = await c.fetchall()
            
    idx = next((i for i, s in enumerate(srv_list) if s['id'] == srv_id), -1)
    if idx == -1: return
    
    if action == "up" and idx > 0:
        other_id = srv_list[idx-1]['id']
        await swap_service_priority(srv_id, other_id)
    elif action == "down" and idx < len(srv_list) - 1:
        other_id = srv_list[idx+1]['id']
        await swap_service_priority(srv_id, other_id)
        
    services = await get_services()
    await callback.message.edit_reply_markup(reply_markup=get_services_admin_kb(services))
    await callback.answer("Приоритет изменен")

# ================= НАСТРОЙКИ =================
@admin_router.callback_query(F.data == "adm_settings")
async def adm_settings_menu(callback: CallbackQuery):
    task_rew = await get_setting('task_reward')
    ref_rew = await get_setting('ref_reward')
    ref_tasks = await get_setting('ref_tasks_needed')
    
    text = (
        f"🛠 <b>Настройки</b>\n\n"
        f"Награда за задание: {task_rew} ⭐\n"
        f"Награда за реферала: {ref_rew} ⭐\n"
        f"Заданий для реферала: {ref_tasks} шт.\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_settings_kb())
    await callback.answer()

@admin_router.callback_query(F.data == "adm_set_task")
async def adm_set_task_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_task_reward)
    await callback.message.edit_text("Введите награду за задание (например 0.65):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_task_reward)
async def adm_set_task_val(message: Message, state: FSMContext):
    await set_setting('task_reward', message.text.replace(",", "."))
    await state.clear()
    await message.answer("✅ Настройка сохранена!", reply_markup=admin_main_kb())

@admin_router.callback_query(F.data == "adm_set_ref")
async def adm_set_ref_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ref_reward)
    await callback.message.edit_text("Введите награду за реферала (например 15):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_ref_reward)
async def adm_set_ref_val(message: Message, state: FSMContext):
    await set_setting('ref_reward', message.text.replace(",", "."))
    await state.clear()
    await message.answer("✅ Настройка сохранена!", reply_markup=admin_main_kb())

@admin_router.callback_query(F.data == "adm_set_reftasks")
async def adm_set_reftasks_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ref_tasks)
    await callback.message.edit_text("Сколько заданий должен выполнить реферал:", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_ref_tasks)
async def adm_set_reftasks_val(message: Message, state: FSMContext):
    if message.text.isdigit():
        await set_setting('ref_tasks_needed', message.text)
        await state.clear()
        await message.answer("✅ Настройка сохранена!", reply_markup=admin_main_kb())
    else:
        await message.answer("❌ Введите целое число.")

# ================= БЭКАП =================
@admin_router.callback_query(F.data == "adm_backup")
async def adm_backup_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_search)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Скачать БД", callback_data="adm_bk_download")],
        [InlineKeyboardButton(text="📤 Загрузить БД", callback_data="adm_bk_upload")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])
    await callback.message.edit_text("💾 <b>Бэкап базы данных</b>", reply_markup=kb)
    await callback.answer()

@admin_router.callback_query(F.data == "adm_bk_download")
async def adm_bk_download(callback: CallbackQuery):
    if os.path.exists(DB_PATH):
        doc = FSInputFile(DB_PATH, filename="bot_backup.db")
        await callback.message.answer_document(doc, caption="✅ Ваш файл базы данных.")
    else:
        await callback.answer("❌ Файл БД не найден.", show_alert=True)
    await callback.answer()

@admin_router.callback_query(F.data == "adm_bk_upload")
async def adm_bk_upload_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_media)
    await callback.message.edit_text("📤 Отправьте файл базы данных (.db) для загрузки:", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.broadcast_media, F.document)
async def adm_bk_upload_file(message: Message, state: FSMContext):
    if not message.document.file_name.endswith(".db"):
        await message.answer("❌ Нужен файл формата .db")
        return
    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, DB_PATH)
    await state.clear()
    await message.answer("✅ База данных успешно загружена и заменена!", reply_markup=admin_main_kb())

# ================= РАССЫЛКА =================
@admin_router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_menu(callback: CallbackQuery, state: FSMContext):
    await state.update_data(bc_text="", bc_media=None, bc_buttons=None)
    await callback.message.edit_text("📢 <b>Рассылка</b>\nНастройте сообщение:", reply_markup=admin_broadcast_kb())
    await callback.answer()

@admin_router.callback_query(F.data == "adm_bc_text")
async def adm_bc_text_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_text)
    await callback.message.edit_text("📝 Отправь текст рассылки (поддерживается HTML):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.broadcast_text)
async def adm_bc_text_set(message: Message, state: FSMContext):
    await state.update_data(bc_text=message.html_text)
    await state.set_state(None)
    await message.answer("✅ Текст добавлен.", reply_markup=admin_broadcast_kb())

@admin_router.callback_query(F.data == "adm_bc_media")
async def adm_bc_media_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_media)
    await callback.message.edit_text("📷 Отправь фото, видео или гиф:", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.broadcast_media, F.photo | F.video | F.animation)
async def adm_bc_media_set(message: Message, state: FSMContext):
    if message.photo:
        await state.update_data(bc_media=("photo", message.photo[-1].file_id))
    elif message.video:
        await state.update_data(bc_media=("video", message.video.file_id))
    elif message.animation:
        await state.update_data(bc_media=("animation", message.animation.file_id))
    await state.set_state(None)
    await message.answer("✅ Медиа добавлено.", reply_markup=admin_broadcast_kb())

@admin_router.callback_query(F.data == "adm_bc_buttons")
async def adm_bc_buttons_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_buttons)
    text = ("🔗 Введи кнопки в формате:\n"
            "<code>Текст - ссылка</code>\n"
            "Для кнопок в один ряд: <code>Текст - ссылка && Текст - ссылка</code>\n"
            "Для новой строки: <code>Текст - ссылка $$ Текст - ссылка</code>")
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.broadcast_buttons)
async def adm_bc_buttons_set(message: Message, state: FSMContext):
    try:
        rows = message.text.split("$$")
        kb_data = []
        for row in rows:
            btns = row.split("&&")
            btn_row = []
            for b in btns:
                parts = b.split(" - ")
                btn_row.append({"text": parts[0].strip(), "url": parts[1].strip()})
            kb_data.append(btn_row)
        await state.update_data(bc_buttons=kb_data)
        await state.set_state(None)
        await message.answer("✅ Кнопки добавлены.", reply_markup=admin_broadcast_kb())
    except:
        await message.answer("❌ Ошибка формата. Пример: Погнали - https://t.me/")

@admin_router.callback_query(F.data == "adm_bc_preview")
async def adm_bc_preview(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('bc_text', '')
    media = data.get('bc_media')
    btns = data.get('bc_buttons')
    
    kb = None
    if btns:
        builder = InlineKeyboardBuilder()
        for row in btns:
            for btn in row:
                builder.button(text=btn['text'], url=btn['url'])
            builder.adjust(*[len(r) for r in btns])
        kb = builder.as_markup()
        
    if media:
        if media[0] == 'photo':
            await callback.message.answer_photo(media[1], caption=text, reply_markup=kb)
        elif media[0] == 'video':
            await callback.message.answer_video(media[1], caption=text, reply_markup=kb)
        elif media[0] == 'animation':
            await callback.message.answer_animation(media[1], caption=text, reply_markup=kb)
    else:
        await callback.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

@admin_router.callback_query(F.data == "adm_bc_send")
async def adm_bc_send(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('bc_text', '')
    media = data.get('bc_media')
    btns = data.get('bc_buttons')
    
    kb = None
    if btns:
        builder = InlineKeyboardBuilder()
        for row in btns:
            for btn in row:
                builder.button(text=btn['text'], url=btn['url'])
            builder.adjust(*[len(r) for r in btns])
        kb = builder.as_markup()
        
    await callback.message.edit_text("⏳ Рассылка запущена...")
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users") as c:
            users = await c.fetchall()
            
    count = 0
    for u in users:
        try:
            if media:
                if media[0] == 'photo':
                    await bot.send_photo(u[0], media[1], caption=text, reply_markup=kb)
                elif media[0] == 'video':
                    await bot.send_video(u[0], media[1], caption=text, reply_markup=kb)
                elif media[0] == 'animation':
                    await bot.send_animation(u[0], media[1], caption=text, reply_markup=kb)
            else:
                await bot.send_message(u[0], text, reply_markup=kb, disable_web_page_preview=True)
            count += 1
        except:
            pass
        await asyncio.sleep(0.05)
        
    await callback.message.answer(f"✅ Рассылка завершена. Успешно: {count}")

@admin_router.callback_query(F.data == "adm_bc_delete")
async def adm_bc_delete(callback: CallbackQuery, state: FSMContext):
    await state.update_data(bc_text="", bc_media=None, bc_buttons=None)
    await callback.message.edit_text("🗑 Данные рассылки удалены. Настройте заново.", reply_markup=admin_broadcast_kb())
    await callback.answer()

# ================= ПОКАЗЫ И ПРИВЕТКА =================
@admin_router.callback_query(F.data == "adm_promos")
async def adm_promos_menu(callback: CallbackQuery):
    await callback.message.edit_text("🖼 <b>Приветка и показы</b>", reply_markup=admin_promos_kb())
    await callback.answer()

@admin_router.callback_query(F.data == "adm_promo_welcome")
async def adm_promo_welcome(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.promo_text)
    await state.update_data(promo_type='welcome')
    await callback.message.edit_text("👋 Отправь текст приветки (HTML):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.callback_query(F.data == "adm_promo_add_show")
async def adm_promo_add_show(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.promo_text)
    await state.update_data(promo_type='show')
    await callback.message.edit_text("🖼 Отправь текст нового показа (HTML):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.promo_text)
async def adm_promo_text_set(message: Message, state: FSMContext):
    await state.update_data(promo_text=message.html_text)
    await state.set_state(AdminStates.promo_media)
    await message.answer("✅ Текст сохранен. Теперь отправь медиа (фото/видео) или напиши 'пропустить':")

@admin_router.message(AdminStates.promo_media)
async def adm_promo_media_set(message: Message, state: FSMContext):
    media = None
    if message.photo: media = ("photo", message.photo[-1].file_id)
    elif message.video: media = ("video", message.video.file_id)
    
    await state.update_data(promo_media=media)
    await state.set_state(AdminStates.promo_buttons)
    await message.answer("✅ Медиа сохранено. Отправь кнопки (или 'пропустить'):")

@admin_router.message(AdminStates.promo_buttons)
async def adm_promo_buttons_set(message: Message, state: FSMContext):
    data = await state.get_data()
    p_type = data['promo_type']
    text = data['promo_text']
    media = data.get('promo_media')
    buttons_json = None
    
    if message.text.lower() != 'пропустить':
        try:
            rows = message.text.split("$$")
            kb_data = []
            for row in rows:
                btns = row.split("&&")
                btn_row = []
                for b in btns:
                    parts = b.split(" - ")
                    btn_row.append({"text": parts[0].strip(), "url": parts[1].strip()})
                kb_data.append(btn_row)
            buttons_json = json.dumps(kb_data)
        except:
            await message.answer("❌ Ошибка кнопок. Попробуй снова.")
            return
            
    await add_promo(p_type, text, media[0] if media else None, media[1] if media else None, buttons_json)
    await state.clear()
    await message.answer("✅ Показ/Приветка успешно сохранены!", reply_markup=admin_main_kb())

@admin_router.callback_query(F.data == "adm_promo_list")
async def adm_promo_list(callback: CallbackQuery):
    shows = await get_all_shows()
    if not shows:
        await callback.answer("Показов пока нет.", show_alert=True)
        return
        
    kb = []
    for s in shows:
        kb.append([InlineKeyboardButton(text=f"Показ #{s['id']}", callback_data=f"adm_pr_del_{s['id']}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_promos")])
    await callback.message.edit_text("Выбери показ для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@admin_router.callback_query(F.data.startswith("adm_pr_del_"))
async def adm_pr_del(callback: CallbackQuery):
    promo_id = int(callback.data.split("_")[3])
    await delete_promo(promo_id)
    await callback.answer("Показ удален!")
    await adm_promos_menu(callback)

# ================= РЕКЛАМА (ТРАФЕРЫ) =================
@admin_router.callback_query(F.data == "adm_ads")
async def adm_ads_menu(callback: CallbackQuery):
    await callback.message.edit_text("📈 <b>Реклама</b>", reply_markup=admin_ads_kb())
    await callback.answer()

@admin_router.callback_query(F.data == "adm_ad_add")
async def adm_ad_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.ad_name)
    await callback.message.edit_text("Введи название (например: savik):", reply_markup=admin_back_kb())
    await callback.answer()

@admin_router.message(AdminStates.ad_name)
async def adm_ad_name(message: Message, state: FSMContext):
    await state.update_data(ad_name=message.text.strip())
    await state.set_state(AdminStates.ad_trafer)
    await message.answer("Введи юз трафера (например: @savikfly):")

@admin_router.message(AdminStates.ad_trafer)
async def adm_ad_trafer(message: Message, state: FSMContext):
    await state.update_data(ad_trafer=message.text.strip())
    await state.set_state(AdminStates.ad_owner)
    await message.answer("Введи юз владельца (например: @trombi):")

@admin_router.message(AdminStates.ad_owner)
async def adm_ad_owner(message: Message, state: FSMContext):
    data = await state.get_data()
    await add_traffic_ad(data['ad_name'], data['ad_trafer'], message.text.strip())
    await state.clear()
    await message.answer(f"✅ Трафер добавлен!\nСтатистика доступна по команде: /stat_{data['ad_name']}", reply_markup=admin_main_kb())

# Отдельный роутер для траферов
traffic_router = Router()

@traffic_router.message(F.text.startswith("/stat_"))
async def traffic_stats(message: Message):
    cmd_name = message.text.split("_", 1)[1]
    
    ad = await get_traffic_ad(cmd_name)
    if not ad:
        return
        
    total, today = await get_traffic_stats(cmd_name)
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    
    is_owner = username == ad['owner'] or message.from_user.id == ADMIN_ID
    is_trafer = username == ad['trafer']
    
    if is_owner or is_trafer:
        text = f"📊 <b>Статистика: {cmd_name}</b>\n\n"
        text += f"Всего привел: {total} чел.\n"
        text += f"За сегодня: {today} чел."
        
        if is_owner:
            text += f"\n\n👑 <b>Полная статистика (Владелец)</b>\n"
            text += f"Трафер: {ad['trafer']}\n"
            text += f"Владелец: {ad['owner']}"
            
        await message.answer(text)
