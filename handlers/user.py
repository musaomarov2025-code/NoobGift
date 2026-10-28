import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

import database as db
import config
import texts
import keyboards
from handlers.tasks import show_tasks_menu

router = Router()
log = logging.getLogger("handlers.user")

_bot_username_cache: str | None = None

async def _bot_username(bot: Bot) -> str:
    global _bot_username_cache
    if not _bot_username_cache:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache

def _greeting_kb(greet: dict):
    buttons = greet.get("buttons") or []
    rows = []
    for row_data in buttons:
        if isinstance(row_data, dict):
            row_data = [row_data]
        row = []
        for btn in row_data:
            if btn.get("text") and btn.get("url"):
                row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
        if row:
            rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

async def _show_greeting(message: Message, bot: Bot):
    greet = await db.get_greeting()
    kb = _greeting_kb(greet)
    text_ = (greet.get("text") or texts.DEFAULT_GREETING).strip()
    media = greet.get("media")

    if media and media.get("file_id"):
        try:
            if media.get("type") == "photo":
                await bot.send_photo(message.chat.id, media["file_id"], caption=text_, reply_markup=kb)
                return
            elif media.get("type") == "video":
                await bot.send_video(message.chat.id, media["file_id"], caption=text_, reply_markup=kb)
                return
        except TelegramBadRequest:
            pass
    await message.answer(text_, reply_markup=kb)

async def _start_core(message: Message, bot: Bot, payload: str = ""):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or ""

    ref_id, promo_code, ad_code = None, None, None
    if payload:
        if payload.isdigit(): ref_id = int(payload)
        elif payload.startswith("promo_"): promo_code = payload[6:]
        elif payload.startswith("ad_"): ad_code = payload[3:]

    user = await db.get_user(user_id)
    is_new = user is None
    if is_new:
        user = await db.create_user(user_id, username, first_name, referrer_id=ref_id, ad_code=ad_code)
    else:
        await db.update_user(user_id, username=username, first_name=first_name)

    if ad_code and is_new:
        await db.incr_ad_stat(ad_code, "clicks")

    if promo_code:
        result = await db.use_promocode(promo_code, user_id)
        if "error" not in result:
            fresh = await db.get_user(user_id)
            await message.answer(texts.promo_activated_text(result["amount"], fresh["balance"]))
        elif result["error"] == "not_found":
            await message.answer(texts.PROMO_NOT_FOUND)
        elif result["error"] == "already_used":
            await message.answer(texts.PROMO_ALREADY_USED)
        elif result["error"] == "limit_reached":
            await message.answer(texts.PROMO_LIMIT_REACHED)

    await _show_greeting(message, bot)
    await asyncio.sleep(4)
    await message.answer(texts.STAR_MESSAGE)
    await asyncio.sleep(4)
    
    # СРАЗУ ЗАДАНИЯ
    user = await db.get_user(user_id)
    try:
        await show_tasks_menu(message, user, bot)
    except Exception as e:
        log.error(f"Ошибка при загрузке заданий: {e}")
        await message.answer("⚠️ Произошла ошибка при загрузке заданий.", reply_markup=keyboards.main_menu_kb())

@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    await _start_core(message, bot, command.args or "")

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await _start_core(message, bot, "")

@router.callback_query(F.data == "back_menu")
async def cb_back_menu(callback: CallbackQuery):
    # Удаляем сообщение, откуда нажали "Назад" (например, "Задания закончились")
    try: 
        await callback.message.delete()
    except: 
        pass
    
    # Отправляем новое сообщение с главным меню
    await callback.message.answer(texts.MENU_TEXT, reply_markup=keyboards.main_menu_kb())
    await callback.answer()

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user: await message.answer(texts.profile_text(user))

@router.message(F.text == "👥 Рефералы")
async def show_referrals(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if not user: return
    bu = await _bot_username(bot)
    ref_p = await db.get_setting("ref_percent", 10)
    await message.answer(texts.referrals_text(bu, user, ref_p), reply_markup=keyboards.referral_kb(bu, user["user_id"]))

@router.callback_query(F.data == "copy_ref")
async def cb_copy_ref(callback: CallbackQuery, bot: Bot):
    bu = await _bot_username(bot)
    link = f"https://t.me/{bu}?start={callback.from_user.id}"
    
    # Отправляем ссылку в рамке (при нажатии на нее в Telegram она копируется)
    await callback.message.answer(
        f"👇 <b>Нажми на ссылку ниже, чтобы скопировать:</b>\n\n"
        f"<code>{link}</code>"
    )
    # Показываем всплывающее окно
    await callback.answer("✅ Ссылка скопирована!", show_alert=True)
@router.message(F.text == "📊 Статистика")

async def show_stats(message: Message, state: FSMContext):
    await state.clear()
    stats = await db.get_stats()
    top = await db.get_top_users(5)
    await message.answer(texts.stats_text(stats, top), reply_markup=keyboards.stats_kb())

@router.message(F.text == "💸 Вывод")
async def show_withdraw(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    if user: await message.answer(texts.withdraw_text(user), reply_markup=keyboards.withdraw_kb())

@router.callback_query(F.data.startswith("withdraw_"))
async def cb_withdraw(callback: CallbackQuery, bot: Bot):
    try: amount = float(callback.data.split("_", 1)[1])
    except: return await callback.answer("Ошибка")

    user = await db.get_user(callback.from_user.id)
    if not user: return await callback.answer("Ошибка")

    if not callback.from_user.username:
        return await callback.answer("⚠️ У вас не установлен @username в Telegram.\nУстановите его в настройках профиля.", show_alert=True)

    if user["balance"] < amount:
        return await callback.answer(f"❌ Недостаточно средств.\nВаш баланс: {user['balance']:.2f} ⭐️", show_alert=True)

    result = await db.create_withdrawal(callback.from_user.id, callback.from_user.username, callback.from_user.first_name or "", amount)
    if "error" in result: return await callback.answer("❌ Ошибка")

    await callback.answer()
    wid = result["id"]
    await callback.message.answer(texts.withdrawal_created_text(wid, amount))

    channel = await db.get_setting("withdraw_channel") or ""
    if channel:
        try:
            msg = await bot.send_message(channel, texts.withdrawal_channel_new_text(wid, callback.from_user.username, callback.from_user.id, amount))
            await db.set_withdrawal_msg(wid, msg.message_id)
        except Exception as e: 
            log.warning(f"channel send err: {e}")
            await callback.message.answer(f"⚠️ Внимание! Не удалось отправить заявку в канал. Проверьте, что бот добавлен в админы канала, и его ID указан верно. Ошибка: {e}")

@router.message(F.text.startswith("/stat_"))
async def cmd_ad_stats(message: Message):
    raw = message.text[len("/stat_"):]
    code = raw.split("@")[0].split()[0].strip() if raw else ""
    if not code: return
    ad = await db.get_ad(code)
    if not ad or ad["owner_id"] != message.from_user.id: return
    await message.answer(texts.ad_stat_text(ad))
