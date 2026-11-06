import asyncio
import json
import logging
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

from ads import post_from_message, send_post, safe_edit
from config import ADMIN_IDS, MSK, DAILY_HOUR_MSK
from database import (
    get_setting, set_setting, all_user_ids, mark_blocked,
)
from keyboards import daily_kb, back_kb

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class DailyForm(StatesGroup):
    text = State()
    btns = State()


# ---------- рассылка ----------

async def broadcast(bot: Bot, post, markup=None):
    """Отправляет пост всем. Возвращает (доставлено, не доставлено)."""
    ok = fail = 0
    for uid in await all_user_ids():
        for attempt in range(2):
            try:
                await send_post(bot, uid, post, markup)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                if attempt == 1:
                    fail += 1
            except TelegramForbiddenError:
                await mark_blocked(uid)
                fail += 1
                break
            except Exception:
                fail += 1
                break
        await asyncio.sleep(0.05)
    return ok, fail


# ---------- ежедневное уведомление ----------

async def build_daily_post():
    text = await get_setting("daily_text")
    ents = json.loads(await get_setting("daily_entities") or "[]")
    return {"kind": "text", "file_id": None, "text": text,
            "entities": ents, "buttons": []}


async def daily_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=await get_setting("daily_btn_ref"),
            callback_data="daily_ref")],
        [InlineKeyboardButton(
            text=await get_setting("daily_btn_tasks"),
            callback_data="daily_tasks")],
    ])


async def daily_loop(bot: Bot):
    """Каждый день в DAILY_HOUR_MSK по Москве."""
    while True:
        now = datetime.now(MSK)
        target = now.replace(
            hour=DAILY_HOUR_MSK, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            if await get_setting("daily_enabled") != "1":
                continue
            today = datetime.now(MSK).strftime("%Y-%m-%d")
            if await get_setting("daily_last") == today:
                continue
            await set_setting("daily_last", today)
            ok, fail = await broadcast(
                bot, await build_daily_post(), await daily_markup())
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"🎯 Ежедневное уведомление отправлено.\n"
                        f"Доставлено: {ok}, не доставлено: {fail}")
                except Exception:
                    pass
        except Exception:
            logging.exception("daily loop error")


# ---------- админка ----------

async def _summary():
    en = await get_setting("daily_enabled") == "1"
    text = (
        "🎯 Ежедневное уведомление\n\n"
        f"Статус: {'включено' if en else 'выключено'}\n"
        f"Время: {DAILY_HOUR_MSK}:00 по Москве\n\n"
        "Выше то, что увидят пользователи.")
    return text, en


async def show_menu(bot: Bot, chat_id):
    await send_post(
        bot, chat_id, await build_daily_post(), await daily_markup())
    text, en = await _summary()
    await bot.send_message(chat_id, text, reply_markup=daily_kb(en))


@router.callback_query(F.data == "adm:daily")
async def daily_menu(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_menu(bot, call.message.chat.id)
    await call.answer()


@router.callback_query(F.data == "daily:toggle")
async def daily_toggle(call: CallbackQuery):
    en = await get_setting("daily_enabled") == "1"
    await set_setting("daily_enabled", "0" if en else "1")
    text, en = await _summary()
    await safe_edit(call, text, daily_kb(en))
    await call.answer()


@router.callback_query(F.data == "daily:text")
async def daily_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(DailyForm.text)
    await call.message.answer(
        "Отправь новый текст сообщением. Жирный шрифт и премиум-эмодзи "
        "сохранятся.", reply_markup=back_kb("adm:daily"))
    await call.answer()


@router.message(DailyForm.text)
async def daily_text_save(message: Message, state: FSMContext, bot: Bot):
    post = post_from_message(message)
    if not post or post["kind"] != "text":
        await message.answer("Нужен именно текст, без фото и видео.")
        return
    await set_setting("daily_text", post["text"])
    await set_setting("daily_entities", json.dumps(
        post["entities"], ensure_ascii=False))
    await state.clear()
    await message.answer("✅ Текст сохранён")
    await show_menu(bot, message.chat.id)


@router.callback_query(F.data == "daily:btns")
async def daily_btns(call: CallbackQuery, state: FSMContext):
    await state.set_state(DailyForm.btns)
    await call.message.answer(
        "Отправь 2 строки:\n1) текст кнопки «пригласить друга»\n"
        "2) текст кнопки «выполнить задания»\n\n"
        "Пример:\n👥 Пригласить друга (+3⭐️)\n🎯 Выполнить задания (+12⭐️)",
        reply_markup=back_kb("adm:daily"))
    await call.answer()


@router.message(DailyForm.btns)
async def daily_btns_save(message: Message, state: FSMContext, bot: Bot):
    lines = [x.strip() for x in (message.text or "").splitlines()
             if x.strip()]
    if len(lines) != 2:
        await message.answer("Нужно ровно 2 строки.")
        return
    await set_setting("daily_btn_ref", lines[0])
    await set_setting("daily_btn_tasks", lines[1])
    await state.clear()
    await message.answer("✅ Кнопки сохранены")
    await show_menu(bot, message.chat.id)


@router.callback_query(F.data == "daily:test")
async def daily_test(call: CallbackQuery, bot: Bot):
    await send_post(bot, call.message.chat.id,
                    await build_daily_post(), await daily_markup())
    await call.answer("Отправил тебе")
