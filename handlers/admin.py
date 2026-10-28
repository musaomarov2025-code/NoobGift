import json
import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
import database as db
import texts
import keyboards
from states import AdminSG
from services.manager import _get_active_services, _SERVICE_CLASSES

router = Router()
log = logging.getLogger("handlers.admin")
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔧 <b>Админ-панель</b>\n\nВыбери раздел:", reply_markup=keyboards.admin_menu_kb())

@router.message(Command("test_api"))
async def cmd_test_api(message: Message):
    await message.answer("⏳ Тестирую API (жду ответы)...")
    services = await _get_active_services()
    if not services:
        return await message.answer("❌ Нет активных сервисов (включи их и добавь ключи в админке).")
    
    # ПОЛУЧАЕМ СЛОВАРЬ ЮЗЕРА ИЗ БАЗЫ (а не просто число)
    user = await db.get_user(message.from_user.id)
    if not user:
        return await message.answer("❌ Юзер не найден в базе. Напиши /start")
    
    res_text = "<b>Результаты API:</b>\n\n"
    for s in services:
        try:
            # Передаем в сервис объект user (словарь)
            tasks = await s.get_tasks(user)
            res_text += f"<b>{s.name}</b>: получено {len(tasks)} заданий.\n"
        except Exception as e:
            res_text += f"<b>{s.name}</b>: ОШИБКА - {e}\n"
    
    await message.answer(res_text)
    
@router.callback_query(F.data == "adm_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🔧 <b>Админ-панель</b>\n\nВыбери раздел:", reply_markup=keyboards.admin_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery): await callback.answer()

# ============= 1. СПОНСОРЫ =============
@router.callback_query(F.data == "adm_services")
async def adm_services(callback: CallbackQuery):
    settings = await db.get_setting("services_enabled", {})
    await callback.message.edit_text("🤝 <b>Спонсоры</b>\n\nНажми, чтобы Вкл/Выкл:", reply_markup=keyboards.admin_services_kb(settings))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_svc_toggle_"))
async def adm_svc_toggle(callback: CallbackQuery):
    service = callback.data.replace("adm_svc_toggle_", "")
    settings = await db.get_setting("services_enabled", {})
    settings[service] = not settings.get(service, False)
    await db.set_setting("services_enabled", settings)
    await adm_services(callback)

@router.callback_query(F.data == "adm_svc_keys")
async def adm_svc_keys(callback: CallbackQuery):
    await callback.message.edit_text("🔑 <b>API-ключи</b>\n\nВыбери сервис:", reply_markup=keyboards.admin_services_keys_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("adm_key_edit_"))
async def adm_key_edit(callback: CallbackQuery, state: FSMContext):
    service = callback.data.replace("adm_key_edit_", "")
    await state.update_data(edit_service=service)
    await state.set_state(AdminSG.service_key)
    current_key = await db.get_service_key(service)
    display_key = f"<code>{current_key}</code>" if current_key else "❌ пусто"
    await callback.message.edit_text(f"🔑 <b>{keyboards.SERVICES[service]}</b>\n\nТекущий: {display_key}\n\nОтправь новый ключ:")
    await callback.answer()

@router.message(AdminSG.service_key)
async def adm_key_save(message: Message, state: FSMContext):
    data = await state.get_data()
    service = data.get("edit_service")
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await db.set_service_key(service, message.text.strip())
    await state.clear()
    await message.answer(f"✅ Ключ для {keyboards.SERVICES[service]} сохранён!", reply_markup=keyboards.admin_menu_kb())

# ============= 2. ЗАЯВКИ =============
@router.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(callback: CallbackQuery):
    pending = await db.list_withdrawals("pending")
    if not pending:
        return await callback.message.edit_text("📋 Нет заявок.", reply_markup=keyboards.admin_back_kb())
    await _show_withdraw_card(callback.message, pending, 0)

async def _show_withdraw_card(message: Message, withdrawals: list, index: int):
    w = withdrawals[index]
    user = await db.get_user(w["user_id"])
    who = f"@{w['username']}" if w["username"] else w["first_name"]
    text_ = (f"📋 <b>Заявка #{w['id']}</b>\n\n👤 {who}\n🆔 <code>{w['user_id']}</code>\n⭐️ Сумма: {w['amount']} ⭐️\n\n"
             f"<b>📊 Инфо:</b>\n• Баланс: {user['balance']:.2f}\n• Заданий: {user['tasks_done']}\n• Рефов: {user['refs_count']}")
    await message.edit_text(text_, reply_markup=keyboards.admin_withdraw_card_kb(w["id"], index, len(withdrawals)))

@router.callback_query(F.data.startswith("adm_wd_nav_"))
async def adm_wd_nav(callback: CallbackQuery):
    index = int(callback.data.split("_")[-1])
    pending = await db.list_withdrawals("pending")
    if not pending: return await callback.answer("Пусто", show_alert=True)
    await _show_withdraw_card(callback.message, pending, index)
    await callback.answer()

@router.callback_query(F.data.startswith("adm_wd_skip_"))
async def adm_wd_skip(callback: CallbackQuery):
    index = int(callback.data.split("_")[-1]) + 1
    pending = await db.list_withdrawals("pending")
    if not pending: return await callback.answer("Пусто", show_alert=True)
    await _show_withdraw_card(callback.message, pending, index % len(pending))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_wd_accept_"))
async def adm_wd_accept(callback: CallbackQuery, bot: Bot):
    wid = int(callback.data.split("_")[-1])
    w = await db.get_withdrawal(wid)
    if not w or w["status"] != "pending": return await callback.answer("Обработана", show_alert=True)
    await db.update_withdrawal(wid, "accepted")
    channel = await db.get_setting("withdraw_channel")
    if channel:
        try: await bot.send_message(channel, texts.withdrawal_channel_paid_text(wid, w["username"], w["user_id"], w["amount"]))
        except: pass
    try: await bot.send_message(w["user_id"], f"✅ Заявка #{wid} выплачена!")
    except: pass
    await callback.message.edit_text(f"✅ Заявка #{wid} принята.", reply_markup=keyboards.admin_back_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("adm_wd_reject_"))
async def adm_wd_reject(callback: CallbackQuery, bot: Bot):
    wid = int(callback.data.split("_")[-1])
    w = await db.get_withdrawal(wid)
    if not w or w["status"] != "pending": return await callback.answer("Обработана", show_alert=True)
    await db.update_withdrawal(wid, "rejected")
    channel = await db.get_setting("withdraw_channel")
    if channel:
        try: await bot.send_message(channel, texts.withdrawal_channel_reject_text(wid, w["username"], w["user_id"], w["amount"]))
        except: pass
    try: await bot.send_message(w["user_id"], texts.withdrawal_rejected_user_text(wid, w["amount"]))
    except: pass
    await callback.message.edit_text(f"❌ Заявка #{wid} отклонена.", reply_markup=keyboards.admin_back_kb())
    await callback.answer()

# ============= 3. ПРИВЕТКА =============
@router.callback_query(F.data == "adm_greeting")
async def adm_greeting(callback: CallbackQuery):
    greet = await db.get_greeting()
    text_ = f"👋 <b>Приветствие</b>\n\n<code>{greet['text']}</code>\n\nМедиа: {'✅' if greet.get('media') else '❌'}\nКнопок: {len(greet.get('buttons', []))}"
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_greeting_kb())
    await callback.answer()

@router.callback_query(F.data == "adm_greet_text")
async def adm_greet_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_text)
    await callback.message.edit_text("Отправь новый текст (/cancel):")
    await callback.answer()

@router.message(AdminSG.greeting_text)
async def adm_greet_text_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await db.set_greeting(text=message.html_text)
    await state.clear()
    await message.answer("✅ Текст обновлён!", reply_markup=keyboards.admin_menu_kb())

@router.callback_query(F.data == "adm_greet_media")
async def adm_greet_media(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_media)
    await callback.message.edit_text("Отправь фото (/cancel):")
    await callback.answer()

@router.message(AdminSG.greeting_media)
async def adm_greet_media_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    if message.photo:
        await db.set_greeting(media={"type": "photo", "file_id": message.photo[-1].file_id})
        await state.clear()
        await message.answer("✅ Медиа обновлено!", reply_markup=keyboards.admin_menu_kb())
    else:
        await message.answer("❌ Отправь фото.")

@router.callback_query(F.data == "adm_greet_button")
async def adm_greet_button(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_button)
    await callback.message.edit_text("Формат: `Текст - https://ссылка`:")
    await callback.answer()

@router.message(AdminSG.greeting_button)
async def adm_greet_button_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    if " - " not in message.text: return await message.answer("❌ Формат: Текст - ссылка")
    parts = message.text.split(" - ", 1)
    greet = await db.get_greeting()
    buttons = greet.get("buttons", [])
    buttons.append({"text": parts[0].strip(), "url": parts[1].strip()})
    await db.set_greeting(buttons=buttons)
    await state.clear()
    await message.answer("✅ Кнопка добавлена!", reply_markup=keyboards.admin_menu_kb())

@router.callback_query(F.data == "adm_greet_clear")
async def adm_greet_clear(callback: CallbackQuery):
    await db.set_greeting(buttons=[])
    await callback.answer("Кнопки очищены", show_alert=True)
    await adm_greeting(callback)

# ============= 4. СТАТИСТИКА =============
@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    stats = await db.get_stats()
    data = await db.export_data()
    users = data.get("users", {})
    hold_total = sum(u.get("hold", 0) for u in users.values())
    withdrawn_total = sum(u.get("total_withdrawn", 0) for u in users.values())
    
    text_ = (f"📊 <b>Подробная статистика</b>\n\n"
             f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
             f"🆕 Новых за сегодня: {stats.get('new_today', 0)}\n"
             f"✅ Заданий (всего): {stats.get('tasks_done_total', 0)}\n"
             f"✅ Заданий сегодня: {stats.get('tasks_done_today', 0)}\n"
             f"✅ Заданий вчера: {stats.get('tasks_done_yesterday', 0)}\n"
             f"👥 Всего рефералов: {stats.get('refs_total', 0)}\n"
             f"❌ Отписалось: {stats.get('unsubscribed_total', 0)}\n"
             f"⏳ В холде: {hold_total:.2f} ⭐️\n"
             f"💎 Выплачено: {withdrawn_total:.2f} ⭐️")
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_back_kb())
    await callback.answer()

# ============= 5. РАССЫЛКА =============
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Создать рассылку", callback_data="adm_bc_setup")],
        [InlineKeyboardButton(text="⏰ Автопост (24ч)", callback_data="adm_ap_setup")],
        [InlineKeyboardButton(text="🚀 Отправить сейчас", callback_data="adm_bc_send")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="adm_bc_clear")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="adm_back")],
    ])
    await callback.message.edit_text("📨 <b>Рассылка</b>", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "adm_bc_setup")
async def adm_bc_setup(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.bc_text)
    await callback.message.edit_text("Отправь текст рассылки (можно с форматированием):")
    await callback.answer()

@router.message(AdminSG.bc_text)
async def adm_bc_text_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await state.update_data(bc_text=message.html_text)
    await state.set_state(AdminSG.bc_media)
    await message.answer("Отправь фото или `-` чтобы пропустить:")

@router.message(AdminSG.bc_media)
async def adm_bc_media_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    media = None
    if message.photo: media = {"type": "photo", "file_id": message.photo[-1].file_id}
    
    await state.update_data(bc_media=media)
    await state.set_state(AdminSG.bc_button)
    await message.answer("Добавь кнопку (формат: `Текст - https://ссылка`) или `-` чтобы пропустить:")

@router.message(AdminSG.bc_button)
async def adm_bc_button_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    buttons = []
    if message.text != "-" and " - " in message.text:
        parts = message.text.split(" - ", 1)
        buttons.append({"text": parts[0].strip(), "url": parts[1].strip()})
        
    await state.update_data(bc_buttons=buttons)
    await state.set_state(AdminSG.bc_count)
    await message.answer("Сколько человек охватить? (число или `all`):")

@router.message(AdminSG.bc_count)
async def adm_bc_count_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    count = 0 if message.text.lower() == "all" else int(message.text)
    data = await state.get_data()
    draft = {"text": data.get("bc_text"), "media": data.get("bc_media"), "buttons": data.get("bc_buttons", []), "count": count}
    await db.set_setting("broadcast_draft", draft)
    await state.clear()
    await message.answer("✅ Черновик сохранён! Нажми «🚀 Отправить сейчас» в меню рассылки.", reply_markup=keyboards.admin_menu_kb())

@router.callback_query(F.data == "adm_bc_clear")
async def adm_bc_clear(callback: CallbackQuery):
    await db.set_setting("broadcast_draft", None)
    await callback.answer("Удалено", show_alert=True)
    await adm_broadcast(callback)

@router.callback_query(F.data == "adm_bc_send")
async def adm_bc_send(callback: CallbackQuery, bot: Bot):
    draft = await db.get_setting("broadcast_draft")
    if not draft: return await callback.answer("❌ Черновик пуст", show_alert=True)
    await callback.message.edit_text("⏳ Отправляю...")
    await callback.answer()
    
    data = await db.export_data()
    users = list(data["users"].keys())
    if draft.get("count", 0) > 0: users = users[:draft["count"]]
    
    kb = None
    if draft.get("buttons"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b["text"], url=b["url"])] for b in draft["buttons"]])
        
    success = 0
    for uid in users:
        try:
            if draft.get("media"):
                await bot.send_photo(uid, draft["media"]["file_id"], caption=draft["text"], reply_markup=kb)
            else:
                await bot.send_message(uid, draft["text"], reply_markup=kb)
            success += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await callback.message.edit_text(f"✅ Отправлено: {success} из {len(users)}", reply_markup=keyboards.admin_back_kb())

@router.callback_query(F.data == "adm_ap_setup")
async def adm_ap_setup(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.ap_text)
    await callback.message.edit_text("Отправь текст для автопоста (каждые 24ч):")
    await callback.answer()

@router.message(AdminSG.ap_text)
async def adm_ap_text_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await db.set_setting("autopost", {"text": message.html_text, "media": None, "enabled": True})
    await state.clear()
    await message.answer("✅ Автопост включён! Бот будет отправлять его каждые 24 часа.", reply_markup=keyboards.admin_menu_kb())

# ============= 6. ПРОМОКОДЫ =============
@router.callback_query(F.data == "adm_promos")
async def adm_promos(callback: CallbackQuery):
    promos = await db.get_promocodes()
    text_ = "🎟 <b>Промокоды</b>\n\n"
    for p in promos[-5:]: text_ += f"• <code>{p['code']}</code> — {p['amount']} ⭐️ ({p['used']}/{p['limit']})\n"
    if not promos: text_ += "Пусто."
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_promos_kb())
    await callback.answer()

@router.callback_query(F.data == "adm_promo_create")
async def adm_promo_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.promo_code)
    await callback.message.edit_text("Отправь название промокода (без пробелов):")
    await callback.answer()

@router.message(AdminSG.promo_code)
async def adm_promo_code_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await state.update_data(promo_code=message.text.strip())
    await state.set_state(AdminSG.promo_amount)
    await message.answer("Сумма (⭐️):")

@router.message(AdminSG.promo_amount)
async def adm_promo_amount_save(message: Message, state: FSMContext):
    try: amount = float(message.text.replace(",", "."))
    except: return await message.answer("❌ Введи число.")
    await state.update_data(promo_amount=amount)
    await state.set_state(AdminSG.promo_limit)
    await message.answer("Лимит активаций (чел):")

@router.message(AdminSG.promo_limit)
async def adm_promo_limit_save(message: Message, state: FSMContext, bot: Bot):
    try: limit = int(message.text)
    except: return await message.answer("❌ Введи число.")
    data = await state.get_data()
    res = await db.create_promocode(data["promo_code"], data["promo_amount"], limit)
    await state.clear()
    if "error" in res: return await message.answer("❌ Ошибка (уже есть).", reply_markup=keyboards.admin_menu_kb())
    me = await bot.get_me()
    await message.answer(f"✅ Создан!\n\nКод: <code>{data['promo_code']}</code>\nСсылка:\n<code>https://t.me/{me.username}?start=promo_{data['promo_code']}</code>", reply_markup=keyboards.admin_menu_kb())

# ============= 7. РЕКЛАМА =============
@router.callback_query(F.data == "adm_ads")
async def adm_ads(callback: CallbackQuery):
    await callback.message.edit_text("📢 <b>Реклама</b>", reply_markup=keyboards.admin_ads_kb())
    await callback.answer()

@router.callback_query(F.data == "adm_ad_create")
async def adm_ad_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.ad_owner)
    await callback.message.edit_text("Введи ID владельца (или `-` если ты):")
    await callback.answer()

@router.message(AdminSG.ad_owner)
async def adm_ad_owner_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    owner = config.ADMIN_ID
    if message.text != "-":
        try: owner = int(message.text)
        except: return await message.answer("❌ ID числом или `-`")
    await state.update_data(ad_owner=owner)
    await state.set_state(AdminSG.ad_name)
    await message.answer("Название рекламы:")

@router.message(AdminSG.ad_name)
async def adm_ad_name_save(message: Message, state: FSMContext):
    await state.update_data(ad_name=message.text)
    await state.set_state(AdminSG.ad_price)
    await message.answer("Цена за переход:")

@router.message(AdminSG.ad_price)
async def adm_ad_price_save(message: Message, state: FSMContext, bot: Bot):
    try: price = float(message.text.replace(",", "."))
    except: return await message.answer("❌ Число.")
    data = await state.get_data()
    ad = await db.create_ad(data["ad_owner"], data["ad_name"], price)
    await state.clear()
    me = await bot.get_me()
    await message.answer(f"✅ Реклама создана!\n\n<code>https://t.me/{me.username}?start=ad_{ad['code']}</code>\n\nСтатистика: <code>/stat_{ad['code']}</code>", reply_markup=keyboards.admin_menu_kb())

@router.callback_query(F.data == "adm_ad_list")
async def adm_ad_list(callback: CallbackQuery, bot: Bot):
    ads = await db.list_ads()
    if not ads: return await callback.answer("Пусто", show_alert=True)
    me = await bot.get_me()
    text_ = "📋 <b>Рекламы:</b>\n\n"
    for ad in ads:
        text_ += f"🔗 {ad['name']} ({ad['code']})\n👤 <code>{ad['owner_id']}</code>\nКлики: {ad['clicks']} | Задания: {ad['tasks_done']}\nСсылка: <code>https://t.me/{me.username}?start=ad_{ad['code']}</code>\n\n"
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_back_kb())
    await callback.answer()

# ============= 8. НАСТРОЙКИ =============
@router.callback_query(F.data == "adm_settings")
async def adm_settings(callback: CallbackQuery):
    ref_p = await db.get_setting("ref_percent", 10)
    reward = await db.get_setting("task_reward", 0.4)
    channel = await db.get_setting("withdraw_channel", "")
    text_ = f"⚙️ <b>Настройки</b>\n\n📊 % с рефералов: <b>{ref_p}%</b>\n⭐️ Цена за задание: <b>{reward} ⭐️</b>\n📢 Канал заявок: <code>{channel or 'не задан'}</code>"
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_settings_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_value(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("adm_set_", "")
    prompts = {"ref_percent": "Новый % (число):", "task_reward": "Новая цена (число):", "withdraw_channel": "ID канала (@name или -100...):"}
    await state.update_data(set_key=key)
    await state.set_state(AdminSG.setting_value)
    await callback.message.edit_text(prompts.get(key, "Значение:"))
    await callback.answer()

@router.message(AdminSG.setting_value)
async def adm_set_value_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    data = await state.get_data()
    key = data.get("set_key")
    val = message.text.strip()
    if key == "ref_percent":
        try: val = int(val)
        except: return await message.answer("❌ Число.")
    elif key == "task_reward":
        try: val = float(val.replace(",", "."))
        except: return await message.answer("❌ Число.")
    await db.set_setting(key, val)
    await state.clear()
    await message.answer("✅ Сохранено!", reply_markup=keyboards.admin_menu_kb())

# ============= 9. ЮЗЕР =============
@router.callback_query(F.data == "adm_user")
async def adm_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.user_search)
    await callback.message.edit_text("👤 Отправь ID или @username юзера:")
    await callback.answer()

@router.message(AdminSG.user_search)
async def adm_user_search(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    query = message.text.strip().replace("@", "")
    data = await db.export_data()
    found = None
    if query.isdigit(): found = data["users"].get(query)
    else:
        for u in data["users"].values():
            if u.get("username") and u["username"].lower() == query.lower(): found = u; break
    await state.clear()
    if not found: return await message.answer("❌ Не найден.", reply_markup=keyboards.admin_menu_kb())
    text_ = (f"👤 <b>Профиль</b>\n\nID: <code>{found['user_id']}</code>\nИмя: {found['first_name']}\nЮзер: @{found['username'] or 'нет'}\n"
             f"Бан: {'ДА' if found.get('is_banned') else 'НЕТ'}\n\n⭐️ Баланс: {found['balance']:.2f}\n⏳ Холд: {found['hold']:.2f}\n"
             f"✅ Заданий: {found['tasks_done']}\n👥 Рефов: {found['refs_count']}")
    await message.answer(text_, reply_markup=keyboards.admin_user_kb(found["user_id"], found.get("is_banned", False)))

@router.callback_query(F.data.startswith("usr_ban_"))
async def adm_user_ban(callback: CallbackQuery):
    uid = int(callback.data.split("_")[-1])
    await db.update_user(uid, is_banned=True)
    await callback.answer("🚫 Забанен", show_alert=True)
    user = await db.get_user(uid)
    await callback.message.edit_reply_markup(reply_markup=keyboards.admin_user_kb(uid, True))

@router.callback_query(F.data.startswith("usr_unban_"))
async def adm_user_unban(callback: CallbackQuery):
    uid = int(callback.data.split("_")[-1])
    await db.update_user(uid, is_banned=False)
    await callback.answer("🔓 Разбанен", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=keyboards.admin_user_kb(uid, False))

@router.callback_query(F.data.startswith("usr_bal_plus_"))
async def adm_user_bal_plus(callback: CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[-1])
    await state.update_data(bal_uid=uid, bal_action="plus")
    await state.set_state(AdminSG.user_balance)
    await callback.message.answer("Введи сумму для НАЧИСЛЕНИЯ:")
    await callback.answer()

@router.callback_query(F.data.startswith("usr_bal_minus_"))
async def adm_user_bal_minus(callback: CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[-1])
    await state.update_data(bal_uid=uid, bal_action="minus")
    await state.set_state(AdminSG.user_balance)
    await callback.message.answer("Введи сумму для СПИСАНИЯ:")
    await callback.answer()

@router.message(AdminSG.user_balance)
async def adm_user_bal_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    data = await state.get_data()
    uid, action = data["bal_uid"], data["bal_action"]
    try: amount = float(message.text.replace(",", "."))
    except: return await message.answer("❌ Число.")
    if action == "minus": amount = -amount
    await db.add_balance(uid, amount)
    await state.clear()
    await message.answer(f"✅ Баланс юзера изменён на {amount} ⭐️", reply_markup=keyboards.admin_menu_kb())

# ============= 10. БЭКАП =============
@router.callback_query(F.data == "adm_backup")
async def adm_backup(callback: CallbackQuery):
    await callback.message.edit_text("💾 <b>Бэкап</b>\n\nСкачай или отправь JSON для восстановления.", reply_markup=keyboards.admin_backup_kb())
    await callback.answer()

@router.callback_query(F.data == "adm_backup_download")
async def adm_backup_download(callback: CallbackQuery, bot: Bot):
    data = await db.export_data()
    filepath = f"{config.BACKUP_DIR}/backup_{int(asyncio.get_event_loop().time())}.json"
    with open(filepath, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    
    try:
        await bot.send_document(chat_id=callback.from_user.id, document=FSInputFile(filepath, filename="users_backup.json"))
    except Exception as e:
        log.error(f"backup send err: {e}")
        await callback.message.answer("❌ Ошибка при отправке файла.")
    await callback.answer()

@router.message(F.document)
async def adm_backup_restore(message: Message, bot: Bot):
    if message.from_user.id != config.ADMIN_ID or not message.document.file_name.endswith(".json"): return
    file = await bot.get_file(message.document.file_id)
    filepath = f"{config.BACKUP_DIR}/restore_tmp.json"
    await bot.download_file(file.file_path, filepath)
    try:
        with open(filepath, "r", encoding="utf-8") as f: new_data = json.load(f)
        await db.import_data(new_data)
        await message.answer("✅ База успешно восстановлена!")
    except Exception as e:
        log.error(f"restore err: {e}")
        await message.answer("❌ Ошибка при восстановлении.")
