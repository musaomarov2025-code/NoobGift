import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import database as db
import config
import texts
import keyboards

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
    for b in buttons:
        text_ = b.get("text", "").strip()
        url_ = b.get("url", "").strip()
        if text_ and url_:
            rows.append([keyboards.InlineKeyboardButton(text=text_, url=url_)])
    return keyboards.InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _show_greeting(message: Message, bot: Bot):
    greet = await db.get_greeting()
    kb = _greeting_kb(greet)
    text_ = (greet.get("text") or texts.DEFAULT_GREETING).strip()
    media = greet.get("media")

    if media and media.get("file_id"):
        file_id = media["file_id"]
        mt = media.get("type")
        try:
            if mt == "photo":
                await bot.send_photo(message.chat.id, file_id, caption=text_, reply_markup=kb)
                return
            if mt == "video":
                await bot.send_video(message.chat.id, file_id, caption=text_, reply_markup=kb)
                return
            if mt == "animation":
                await bot.send_animation(message.chat.id, file_id, caption=text_, reply_markup=kb)
                return
        except TelegramBadRequest as e:
            log.warning(f"greeting media failed: {e}")

    await message.answer(text_, reply_markup=kb)


async def _start_core(message: Message, bot: Bot, payload: str = ""):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or ""

    ref_id = None
    promo_code = None
    ad_code = None

    if payload:
        if payload.isdigit():
            ref_id = int(payload)
        elif payload.startswith("promo_"):
            promo_code = payload[6:]
        elif payload.startswith("ad_"):
            ad_code = payload[3:]

    user = await db.get_user(user_id)
    is_new = user is None
    if is_new:
        user = await db.create_user(user_id, username, first_name, referrer_id=ref_id)
    else:
        await db.update_user(user_id, username=username, first_name=first_name)

    if ad_code:
        try:
            await db.incr_ad_stat(ad_code, "clicks")
        except Exception:
            pass

    if promo_code and is_new:
        result = await db.use_promocode(promo_code, user_id)
        if "error" not in result:
            fresh = await db.get_user(user_id)
            await message.answer(
                texts.promo_activated_text(result["amount"], fresh["balance"])
            )
        elif result["error"] == "not_found":
            await message.answer(texts.PROMO_NOT_FOUND)
        # already_used / limit_reached — при первом старте не встретится

    await _show_greeting(message, bot)
    await asyncio.sleep(4)
    await message.answer(texts.STAR_MESSAGE)
    await asyncio.sleep(4)
    await message.answer(texts.MENU_TEXT, reply_markup=keyboards.main_menu_kb())


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, command: CommandObject, bot: Bot):
    await _start_core(message, bot, command.args or "")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await _start_core(message, bot, "")


# ================ ПРОФИЛЬ ================

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    await message.answer(texts.profile_text(user))


# ================ РЕФЕРАЛЫ ================

@router.message(F.text == "👥 Рефералы")
async def show_referrals(message: Message, bot: Bot):
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    bu = await _bot_username(bot)
    await message.answer(
        texts.referrals_text(bu, user),
        reply_markup=keyboards.referral_kb(bu, user["user_id"]),
    )


@router.callback_query(F.data == "copy_ref")
async def cb_copy_ref(callback: CallbackQuery, bot: Bot):
    bu = await _bot_username(bot)
    link = f"https://t.me/{bu}?start={callback.from_user.id}"
    await callback.answer(f"✅ Ссылка скопирована!\n{link}", show_alert=True)


# ================ ВЫВОД ================

@router.message(F.text == "💸 Вывод")
async def show_withdraw(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    await message.answer(texts.withdraw_text(user), reply_markup=keyboards.withdraw_kb())


@router.callback_query(F.data.startswith("withdraw_"))
async def cb_withdraw(callback: CallbackQuery, bot: Bot):
    try:
        amount = float(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка")
        return

    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка")
        return

    if not callback.from_user.username:
        await callback.answer(
            "⚠️ У вас не установлен @username в Telegram.\n"
            "Установите его в настройках профиля, иначе вывод невозможен.",
            show_alert=True,
        )
        return

    if user["balance"] < amount:
        await callback.answer(
            f"❌ Недостаточно средств.\nВаш баланс: {user['balance']:.2f} ⭐️",
            show_alert=True,
        )
        return

    result = await db.create_withdrawal(
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name or "",
        amount,
    )
    if "error" in result:
        await callback.answer("❌ Не удалось создать заявку")
        return

    await callback.answer()
    wid = result["id"]
    await callback.message.answer(texts.withdrawal_created_text(wid, amount))

    channel = await db.get_setting("withdraw_channel") or ""
    if channel:
        try:
            msg = await bot.send_message(
                channel,
                texts.withdrawal_channel_new_text(
                    wid, callback.from_user.username,
                    callback.from_user.id, amount,
                ),
            )
            await db.set_withdrawal_msg(wid, msg.message_id)
        except Exception as e:
            log.warning(f"withdraw channel send failed: {e}")


# ================ СТАТИСТИКА ================

@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    stats = await db.get_stats()
    top = await db.get_top_users(5)
    await message.answer(texts.stats_text(stats, top))


# ================ РЕКЛАМА: /stat_xxx ================

@router.message(F.text.startswith("/stat_"))
async def cmd_ad_stats(message: Message):
    if not message.text:
        return
    raw = message.text[len("/stat_"):]
    code = raw.split("@")[0].split()[0].strip() if raw else ""
    if not code:
        return
    ad = await db.get_ad(code)
    if not ad:
        return
    if ad["owner_id"] != message.from_user.id:
        return  # тихий игнор — не владелец
    await message.answer(texts.ad_stat_text(ad))
