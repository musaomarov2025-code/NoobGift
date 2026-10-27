import json
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

import config
import database as db
import texts
import keyboards
from states import AdminSG

router = Router()
log = logging.getLogger("handlers.admin")

# Фильтр: только админ
router.message.filter(F.from_user.id == config.ADMIN_ID)
router.callback_query.filter(F.from_user.id == config.ADMIN_ID)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔧 <b>Админ-панель</b>\n\nВыбери раздел:", reply_markup=keyboards.admin_menu_kb())


@router.callback_query(F.data == "adm_back")
async def cb_admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🔧 <b>Админ-панель</b>\n\nВыбери раздел:", reply_markup=keyboards.admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ============= 1. СПОНСОРЫ =============

@router.callback_query(F.data == "adm_services")
async def adm_services(callback: CallbackQuery):
    enabled = (await db.get_stats()).get("services_enabled", {})
    # Запрашиваем актуальные настройки из БД
    settings = await db.get_setting("services_enabled", {})
    await callback.message.edit_text(
        "🤝 <b>Управление спонсорами</b>\n\nНажми на сервис, чтобы включить/выключить:",
        reply_markup=keyboards.admin_services_kb(settings)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_svc_toggle_"))
async def adm_svc_toggle(callback: CallbackQuery):
    service = callback.data.replace("adm_svc_toggle_", "")
    settings = await db.get_setting("services_enabled", {})
    current = settings.get(service, False)
    settings[service] = not current
    await db.set_setting("services_enabled", settings)
    await adm_services(callback)


@router.callback_query(F.data == "adm_svc_keys")
async def adm_svc_keys(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔑 <b>API-ключи</b>\n\nВыбери сервис для изменения ключа:",
        reply_markup=keyboards.admin_services_keys_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_key_edit_"))
async def adm_key_edit(callback: CallbackQuery, state: FSMContext):
    service = callback.data.replace("adm_key_edit_", "")
    await state.update_data(edit_service=service)
    await state.set_state(AdminSG.service_key)
    
    current_key = await db.get_service_key(service)
    display_key = f"<code>{current_key}</code>" if current_key else "❌ не задан"
    
    await callback.message.edit_text(
        f"🔑 <b>Ключ для {keyboards.SERVICES[service]}</b>\n\n"
        f"Текущий ключ: {display_key}\n\n"
        f"Отправь новый ключ текстом (или /cancel):"
    )
    await callback.answer()


@router.message(AdminSG.service_key)
async def adm_key_save(message: Message, state: FSMContext):
    data = await state.get_data()
    service = data.get("edit_service")
    if not service:
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
        return

    await db.set_service_key(service, message.text.strip())
    await state.clear()
    await message.answer(f"✅ Ключ для {keyboards.SERVICES[service]} сохранён!", reply_markup=keyboards.admin_menu_kb())


# ============= 2. ЗАЯВКИ =============

@router.callback_query(F.data == "adm_withdrawals")
async def adm_withdrawals(callback: CallbackQuery):
    pending = await db.list_withdrawals("pending")
    if not pending:
        await callback.message.edit_text("📋 Нет активных заявок на вывод.", reply_markup=keyboards.admin_back_kb())
        await callback.answer()
        return
    await _show_withdraw_card(callback.message, pending, 0)


async def _show_withdraw_card(message: Message, withdrawals: list, index: int):
    w = withdrawals[index]
    user = await db.get_user(w["user_id"])
    
    who = f"@{w['username']}" if w["username"] else w["first_name"]
    
    text_ = (
        f"📋 <b>Заявка #{w['id']}</b>\n\n"
        f"👤 Пользователь: {who}\n"
        f"🆔 ID: <code>{w['user_id']}</code>\n"
        f"⭐️ Сумма: <b>{w['amount']} ⭐️</b>\n\n"
        f"<b>📊 Статистика юзера:</b>\n"
        f"• Баланс сейчас: {user['balance']:.2f} ⭐️\n"
        f"• Всего заработал: {user['tasks_done'] * 0.4:.2f} ⭐️\n"
        f"• Заданий выполнил: {user['tasks_done']}\n"
        f"• Пригласил рефералов: {user['refs_count']} чел.\n"
        f"• Заработали рефы: {user['refs_earned']:.2f} ⭐️\n"
    )
    
    kb = keyboards.admin_withdraw_card_kb(w["id"], index, len(withdrawals))
    await message.edit_text(text_, reply_markup=kb)


@router.callback_query(F.data.startswith("adm_wd_nav_"))
async def adm_wd_nav(callback: CallbackQuery):
    index = int(callback.data.split("_")[-1])
    pending = await db.list_withdrawals("pending")
    if not pending:
        await callback.message.edit_text("📋 Нет активных заявок.", reply_markup=keyboards.admin_back_kb())
        await callback.answer()
        return
    await _show_withdraw_card(callback.message, pending, index)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_wd_skip_"))
async def adm_wd_skip(callback: CallbackQuery):
    index = int(callback.data.split("_")[-1]) + 1
    pending = await db.list_withdrawals("pending")
    if not pending:
        await callback.message.edit_text("📋 Нет активных заявок.", reply_markup=keyboards.admin_back_kb())
        await callback.answer()
        return
    await _show_withdraw_card(callback.message, pending, index % len(pending))
    await callback.answer()


@router.callback_query(F.data.startswith("adm_wd_accept_"))
async def adm_wd_accept(callback: CallbackQuery, bot: Bot):
    wid = int(callback.data.split("_")[-1])
    w = await db.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    
    await db.update_withdrawal(wid, "accepted")
    
    # Уведомляем канал
    channel = await db.get_setting("withdraw_channel")
    if channel:
        try:
            await bot.send_message(
                channel,
                texts.withdrawal_channel_paid_text(wid, w["username"], w["user_id"], w["amount"])
            )
        except Exception as e:
            log.error(f"channel send error: {e}")

    # Уведомляем юзера
    try:
        await bot.send_message(w["user_id"], f"✅ Ваша заявка #{wid} на {w['amount']} ⭐️ успешно выплачена!")
    except Exception:
        pass

    await callback.message.edit_text(f"✅ Заявка #{wid} принята и выплачена.", reply_markup=keyboards.admin_back_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("adm_wd_reject_"))
async def adm_wd_reject(callback: CallbackQuery, bot: Bot):
    wid = int(callback.data.split("_")[-1])
    w = await db.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return
    
    await db.update_withdrawal(wid, "rejected")
    
    channel = await db.get_setting("withdraw_channel")
    if channel:
        try:
            await bot.send_message(
                channel,
                texts.withdrawal_channel_reject_text(wid, w["username"], w["user_id"], w["amount"])
            )
        except Exception as e:
            log.error(f"channel send error: {e}")

    try:
        await bot.send_message(w["user_id"], texts.withdrawal_rejected_user_text(wid, w["amount"]))
    except Exception:
        pass

    await callback.message.edit_text(f"❌ Заявка #{wid} отклонена.", reply_markup=keyboards.admin_back_kb())
    await callback.answer()


# ============= 3. ПРИВЕТКА =============

@router.callback_query(F.data == "adm_greeting")
async def adm_greeting(callback: CallbackQuery):
    greet = await db.get_greeting()
    text_ = f"👋 <b>Настройка приветствия</b>\n\nТекущий текст:\n<code>{greet['text']}</code>\n\nМедиа: {'✅ Есть' if greet.get('media') else '❌ Нет'}\nКнопок: {len(greet.get('buttons', []))}"
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_greeting_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_greet_text")
async def adm_greet_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_text)
    await callback.message.edit_text("Отправь новый текст приветствия (или /cancel):")
    await callback.answer()


@router.message(AdminSG.greeting_text)
async def adm_greet_text_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    await db.set_greeting(text=message.text)
    await state.clear()
    await message.answer("✅ Текст обновлён!", reply_markup=keyboards.admin_menu_kb())


@router.callback_query(F.data == "adm_greet_media")
async def adm_greet_media(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_media)
    await callback.message.edit_text("Отправь фото/видео (или /cancel):")
    await callback.answer()


@router.message(AdminSG.greeting_media)
async def adm_greet_media_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    if message.photo:
        await db.set_greeting(media={"type": "photo", "file_id": message.photo[-1].file_id})
    elif message.video:
        await db.set_greeting(media={"type": "video", "file_id": message.video.file_id})
    else:
        return await message.answer("❌ Отправь фото или видео.")
        
    await state.clear()
    await message.answer("✅ Медиа обновлено!", reply_markup=keyboards.admin_menu_kb())


@router.callback_query(F.data == "adm_greet_button")
async def adm_greet_button(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.greeting_button)
    await callback.message.edit_text("Отправь кнопку в формате: `Текст - https://ссылка`\n(цвета в Telegram API для inline-кнопок недоступны):")
    await callback.answer()


@router.message(AdminSG.greeting_button)
async def adm_greet_button_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    if " - " not in message.text:
        return await message.answer("❌ Формат: Текст - ссылка")
    
    parts = message.text.split(" - ", 1)
    btn = {"text": parts[0].strip(), "url": parts[1].strip()}
    
    greet = await db.get_greeting()
    buttons = greet.get("buttons", [])
    buttons.append(btn)
    await db.set_greeting(buttons=buttons)
    
    await state.clear()
    await message.answer("✅ Кнопка добавлена!", reply_markup=keyboards.admin_menu_kb())


@router.callback_query(F.data == "adm_greet_clear")
async def adm_greet_clear(callback: CallbackQuery):
    await db.set_greeting(buttons=[])
    await callback.answer("✅ Кнопки очищены", show_alert=True)
    await adm_greeting(callback)


# ============= 4. СТАТИСТИКА =============

@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    stats = await db.get_stats()
    data = await db.export_data()
    
    users = data.get("users", {})
    hold_total = sum(u.get("hold", 0) for u in users.values())
    withdrawn_total = sum(u.get("total_withdrawn", 0) for u in users.values())
    
    text_ = (
        "📊 <b>Подробная статистика</b>\n\n"
        f"👥 Всего пользователей: {stats.get('total_users', 0)}\n"
        f"🆕 Новых за сегодня: {stats.get('new_today', 0)}\n"
        f"✅ Заданий выполнено (всего): {stats.get('tasks_done_total', 0)}\n"
        f"✅ Заданий сегодня: {stats.get('tasks_done_today', 0)}\n"
        f"✅ Заданий вчера: {stats.get('tasks_done_yesterday', 0)}\n"
        f"👥 Всего рефералов: {stats.get('refs_total', 0)}\n"
        f"❌ Отписалось (штрафы): {stats.get('unsubscribed_total', 0)}\n"
        f"⏳ В холде (сейчас): {hold_total:.2f} ⭐️\n"
        f"💎 Выплачено (всего): {withdrawn_total:.2f} ⭐️"
    )
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_back_kb())
    await callback.answer()
  # ============= 5. РАССЫЛКА И АВТОПОСТ =============

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Настроить рассылку", callback_data="adm_bc_setup")],
        [InlineKeyboardButton(text="⏰ Автопост (каждые 24ч)", callback_data="adm_ap_setup")],
        [InlineKeyboardButton(text="🚀 Отправить рассылку", callback_data="adm_bc_send")],
        [InlineKeyboardButton(text="🗑 Удалить рассылку", callback_data="adm_bc_clear")],
        [InlineKeyboardButton(text="🔙 В админ-меню", callback_data="adm_back")],
    ])
    await callback.message.edit_text("📨 <b>Управление рассылкой</b>\n\nВыбери действие:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm_bc_setup")
async def adm_bc_setup(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.bc_text)
    await callback.message.edit_text("Отправь текст рассылки (или /cancel):")
    await callback.answer()


@router.message(AdminSG.bc_text)
async def adm_bc_text_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    await state.update_data(bc_text=message.html_text)
    await state.set_state(AdminSG.bc_media)
    await message.answer("Отправь фото/видео для рассылки (или напиши `-` чтобы пропустить):")


@router.message(AdminSG.bc_media)
async def adm_bc_media_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    media = None
    if message.photo:
        media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        media = {"type": "video", "file_id": message.video.file_id}
    
    await state.update_data(bc_media=media)
    await state.set_state(AdminSG.bc_count)
    await message.answer("Сколько человек охватить? (напиши число или `all` для всех):")


@router.message(AdminSG.bc_count)
async def adm_bc_count_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    count = 0
    if message.text.lower() == "all":
        count = 0
    else:
        try:
            count = int(message.text)
        except ValueError:
            return await message.answer("❌ Введи число или `all`")
    
    data = await state.get_data()
    draft = {
        "text": data.get("bc_text"),
        "media": data.get("bc_media"),
        "buttons": [],
        "count": count
    }
    await db.set_setting("broadcast_draft", draft)
    await state.clear()
    
    await message.answer("✅ Черновик рассылки сохранён!\nТеперь можешь нажать «🚀 Отправить рассылку».", reply_markup=keyboards.admin_menu_kb())


@router.callback_query(F.data == "adm_bc_clear")
async def adm_bc_clear(callback: CallbackQuery):
    await db.set_setting("broadcast_draft", None)
    await callback.answer("🗑 Черновик рассылки удалён", show_alert=True)
    await adm_broadcast(callback)


@router.callback_query(F.data == "adm_bc_send")
async def adm_bc_send(callback: CallbackQuery, bot: Bot):
    draft = await db.get_setting("broadcast_draft")
    if not draft:
        await callback.answer("❌ Сначала создай рассылку!", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Рассылка запущена...")
    await callback.answer()
    
    data = await db.export_data()
    users = list(data["users"].keys())
    
    limit = draft.get("count", 0)
    if limit > 0:
        users = users[:limit]
    
    success = 0
    for uid in users:
        try:
            if draft.get("media"):
                if draft["media"]["type"] == "photo":
                    await bot.send_photo(uid, draft["media"]["file_id"], caption=draft["text"])
                elif draft["media"]["type"] == "video":
                    await bot.send_video(uid, draft["media"]["file_id"], caption=draft["text"])
            else:
                await bot.send_message(uid, draft["text"])
            success += 1
            await asyncio.sleep(0.05) # защита от FloodWait
        except Exception:
            pass
            
    await callback.message.edit_text(f"✅ Рассылка завершена!\nДоставлено: {success} из {len(users)}", reply_markup=keyboards.admin_back_kb())


# --- Автопост ---

@router.callback_query(F.data == "adm_ap_setup")
async def adm_ap_setup(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.ap_text)
    await callback.message.edit_text("Отправь текст для автопоста (или /cancel):")
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
    if not promos:
        text_ += "Пока нет созданных промокодов."
    else:
        for p in promos[-5:]:
            text_ += f"• <code>{p['code']}</code> — {p['amount']} ⭐️ ({p['used']}/{p['limit']})\n"
    
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_promos_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_promo_create")
async def adm_promo_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.promo_code)
    await callback.message.edit_text("Отправь название промокода (латиницей без пробелов):")
    await callback.answer()


@router.message(AdminSG.promo_code)
async def adm_promo_code_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    await state.update_data(promo_code=message.text.strip())
    await state.set_state(AdminSG.promo_amount)
    await message.answer("Введи сумму (сколько ⭐️ начислить):")


@router.message(AdminSG.promo_amount)
async def adm_promo_amount_save(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число.")
    
    await state.update_data(promo_amount=amount)
    await state.set_state(AdminSG.promo_limit)
    await message.answer("Введи лимит активаций (сколько человек могут использовать):")


@router.message(AdminSG.promo_limit)
async def adm_promo_limit_save(message: Message, state: FSMContext, bot: Bot):
    try:
        limit = int(message.text)
    except ValueError:
        return await message.answer("❌ Введи целое число.")
    
    data = await state.get_data()
    code = data["promo_code"]
    amount = data["promo_amount"]
    
    res = await db.create_promocode(code, amount, limit)
    await state.clear()
    
    if "error" in res:
        return await message.answer("❌ Ошибка: возможно, такой промокод уже существует.", reply_markup=keyboards.admin_menu_kb())
    
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=promo_{code}"
    
    await message.answer(
        f"✅ Промокод создан!\n\n"
        f"Код: <code>{code}</code>\n"
        f"Сумма: {amount} ⭐️\n"
        f"Лимит: {limit} чел.\n\n"
        f"🔗 Ссылка:\n<code>{link}</code>",
        reply_markup=keyboards.admin_menu_kb()
    )


# ============= 7. РЕКЛАМА =============

@router.callback_query(F.data == "adm_ads")
async def adm_ads(callback: CallbackQuery):
    await callback.message.edit_text("📢 <b>Управление рекламой</b>", reply_markup=keyboards.admin_ads_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_ad_create")
async def adm_ad_create(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.ad_owner)
    await callback.message.edit_text("Введи ID владельца рекламы (или отправь `-` если реклама твоя):")
    await callback.answer()


@router.message(AdminSG.ad_owner)
async def adm_ad_owner_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    owner = config.ADMIN_ID
    if message.text != "-":
        try:
            owner = int(message.text)
        except ValueError:
            return await message.answer("❌ Введи ID числом или `-`")
    
    await state.update_data(ad_owner=owner)
    await state.set_state(AdminSG.ad_name)
    await message.answer("Введи название рекламы (для отображения в статистике):")


@router.message(AdminSG.ad_name)
async def adm_ad_name_save(message: Message, state: FSMContext):
    await state.update_data(ad_name=message.text)
    await state.set_state(AdminSG.ad_price)
    await message.answer("Введи цену за переход (числом):")


@router.message(AdminSG.ad_price)
async def adm_ad_price_save(message: Message, state: FSMContext, bot: Bot):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число.")
    
    data = await state.get_data()
    ad = await db.create_ad(data["ad_owner"], data["ad_name"], price)
    await state.clear()
    
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ad_{ad['code']}"
    
    await message.answer(
        f"✅ Реклама создана!\n\n"
        f"Название: {ad['name']}\n"
        f"Владелец: <code>{ad['owner_id']}</code>\n"
        f"Цена за переход: {ad['price']} ⭐️\n\n"
        f"🔗 Ссылка для рекламы:\n<code>{link}</code>\n\n"
        f"📊 Статистика (команда для владельца):\n<code>/stat_{ad['code']}</code>",
        reply_markup=keyboards.admin_menu_kb()
    )


@router.callback_query(F.data == "adm_ad_list")
async def adm_ad_list(callback: CallbackQuery, bot: Bot):
    ads = await db.list_ads()
    if not ads:
        return await callback.answer("Список пуст", show_alert=True)
    
    me = await bot.get_me()
    text_ = "📋 <b>Список реклам:</b>\n\n"
    for ad in ads:
        text_ += f"🔗 {ad['name']} ({ad['code']})\n"
        text_ += f"👤 Владелец: <code>{ad['owner_id']}</code>\n"
        text_ += f"Клики: {ad['clicks']} | Задания: {ad['tasks_done']}\n"
        text_ += f"Ссылка: <code>https://t.me/{me.username}?start=ad_{ad['code']}</code>\n\n"
    
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_back_kb())
    await callback.answer()


# ============= 8. НАСТРОЙКИ =============

@router.callback_query(F.data == "adm_settings")
async def adm_settings(callback: CallbackQuery):
    ref_p = await db.get_setting("ref_percent", 10)
    reward = await db.get_setting("task_reward", 0.4)
    channel = await db.get_setting("withdraw_channel", "")
    
    text_ = (
        "⚙️ <b>Настройки бота</b>\n\n"
        f"📊 % с рефералов: <b>{ref_p}%</b>\n"
        f"⭐️ Цена за задание: <b>{reward} ⭐️</b>\n"
        f"📢 Канал заявок: <code>{channel or 'не задан'}</code>"
    )
    await callback.message.edit_text(text_, reply_markup=keyboards.admin_settings_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_value(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("adm_set_", "")
    
    prompts = {
        "ref_percent": "Введи новый процент с рефералов (только число, например `10`):",
        "task_reward": "Введи новую цену за задание (например `0.44`):",
        "withdraw_channel": "Отправь ID или @username канала для заявок (бот должен быть админом):"
    }
    
    await state.update_data(set_key=key)
    await state.set_state(AdminSG.setting_value)
    await callback.message.edit_text(prompts.get(key, "Введи новое значение:"))
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
        except ValueError: return await message.answer("❌ Нужно целое число.")
    elif key == "task_reward":
        try: val = float(val.replace(",", "."))
        except ValueError: return await message.answer("❌ Нужно число.")
    
    await db.set_setting(key, val)
    await state.clear()
    await message.answer("✅ Настройка сохранена!", reply_markup=keyboards.admin_menu_kb())


# ============= 9. ЮЗЕР =============

@router.callback_query(F.data == "adm_user")
async def adm_user(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminSG.user_search)
    await callback.message.edit_text("👤 Отправь ID или @username пользователя:")
    await callback.answer()


@router.message(AdminSG.user_search)
async def adm_user_search(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=keyboards.admin_menu_kb())
    
    query = message.text.strip().replace("@", "")
    data = await db.export_data()
    found = None
    
    if query.isdigit():
        found = data["users"].get(query)
    else:
        for u in data["users"].values():
            if u.get("username") and u["username"].lower() == query.lower():
                found = u
                break
                
    await state.clear()
    
    if not found:
        return await message.answer("❌ Пользователь не найден.", reply_markup=keyboards.admin_menu_kb())
    
    text_ = (
        f"👤 <b>Профиль юзера</b>\n\n"
        f"ID: <code>{found['user_id']}</code>\n"
        f"Имя: {found['first_name']}\n"
        f"Юзернейм: @{found['username'] or 'нет'}\n"
        f"Дата рег: {found['reg_date'][:10]}\n\n"
        f"⭐️ Баланс: {found['balance']:.2f}\n"
        f"⏳ В холде: {found['hold']:.2f}\n"
        f"💎 Выведено: {found['total_withdrawn']:.2f}\n"
        f"✅ Заданий: {found['tasks_done']}\n\n"
        f"👥 Рефералов: {found['refs_count']}\n"
        f"💰 Доход с рефов: {found['refs_earned']:.2f}"
    )
    await message.answer(text_, reply_markup=keyboards.admin_back_kb())


# ============= 10. БЭКАП =============

@router.callback_query(F.data == "adm_backup")
async def adm_backup(callback: CallbackQuery):
    await callback.message.edit_text("💾 <b>Резервное копирование</b>\n\nСкачай файл или отправь боту ранее сохранённый JSON для восстановления.", reply_markup=keyboards.admin_backup_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_backup_download")
async def adm_backup_download(callback: CallbackQuery):
    data = await db.export_data()
    filepath = f"{config.BACKUP_DIR}/backup_{int(asyncio.get_event_loop().time())}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    await callback.message.answer_document(FSInputFile(filepath, filename="users_backup.json"))
    await callback.answer("✅ Бэкап отправлен")


# Приём файла для восстановления
@router.message(F.document)
async def adm_backup_restore(message: Message, bot: Bot):
    if message.from_user.id != config.ADMIN_ID:
        return
    if not message.document.file_name.endswith(".json"):
        return
    
    file = await bot.get_file(message.document.file_id)
    filepath = f"{config.BACKUP_DIR}/restore_tmp.json"
    await bot.download_file(file.file_path, filepath)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            new_data = json.load(f)
        await db.import_data(new_data)
        await message.answer("✅ База данных успешно восстановлена из файла!")
    except Exception as e:
        log.error(f"restore error: {e}")
        await message.answer("❌ Ошибка при восстановлении базы. Проверь формат файла.")
