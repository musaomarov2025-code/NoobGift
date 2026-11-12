import asyncio
import json
import logging
from datetime import datetime, timedelta
from html import escape

from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)

import sponsors
from ads import STYLES, post_from_message, safe_edit, send_post
from config import (
    ADMIN_IDS, DAILY_HOUR_MSK, MSK, REMIND_HOUR_MSK, REPORT_HOUR_MSK,
    fmt, fmt_bal,
)
from database import (
    all_user_ids, day_start, get_setting, get_sponsors, mark_blocked,
    mark_reminded, remind_candidates, report_stats, set_setting,
)
from keyboards import b, back_kb, color_kb, daily_kb, rem_kb

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class DailyForm(StatesGroup):
    text = State()
    btns = State()


class RemForm(StatesGroup):
    t1 = State()
    t0 = State()


def _btn(text, data, style):
    kw = {"style": style} if style in STYLES else {}
    return InlineKeyboardButton(text=text, callback_data=data, **kw)


async def _sleep_until(hour):
    now = datetime.now(MSK)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


async def _tell_admins(bot: Bot, text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


# ---------- рассылка ----------

async def broadcast(bot: Bot, post, markup=None, ids=None):
    """Отправляет пост списку ids (по умолчанию всем). Стикер из поста
    уходит перед ним (это делает send_post).
    Возвращает (доставлено, не доставлено)."""
    ok = fail = 0
    for uid in (ids if ids is not None else await all_user_ids()):
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
            "entities": ents, "buttons": [], "sticker": None}


async def daily_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn(await get_setting("daily_btn_ref"), "daily_ref",
              await get_setting("daily_style_ref"))],
        [_btn(await get_setting("daily_btn_tasks"), "daily_tasks",
              await get_setting("daily_style_tasks"))],
    ])


async def daily_loop(bot: Bot):
    """Каждый день в DAILY_HOUR_MSK по Москве."""
    while True:
        await _sleep_until(DAILY_HOUR_MSK)
        try:
            if await get_setting("daily_enabled") != "1":
                continue
            today = datetime.now(MSK).strftime("%Y-%m-%d")
            if await get_setting("daily_last") == today:
                continue
            await set_setting("daily_last", today)
            ok, fail = await broadcast(
                bot, await build_daily_post(), await daily_markup())
            await _tell_admins(
                bot, f"🎯 Ежедневное уведомление отправлено.\n"
                     f"Доставлено: {ok}, не доставлено: {fail}")
        except Exception:
            logging.exception("daily loop error")


# ---------- напоминание неактивным ----------

async def reminder_text(first_name, balance):
    key = "remind_text" if balance > 0 else "remind_text_zero"
    text = await get_setting(key)
    reward = await get_setting("task_reward")
    return (text.replace("{name}", escape(first_name or "друг"))
            .replace("{balance}", fmt_bal(balance))
            .replace("{reward}", fmt(reward)))


async def reminder_markup():
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(
        "💎 Выполнить задания", "daily_tasks",
        await get_setting("remind_style"))]])


async def send_reminder(bot: Bot, chat_id, first_name, balance):
    await bot.send_message(
        chat_id, await reminder_text(first_name, balance),
        parse_mode="HTML", reply_markup=await reminder_markup())


async def run_reminders(bot: Bot):
    """None, если выключено; иначе (доставлено, не доставлено)."""
    if await get_setting("remind_enabled") != "1":
        return None
    ok = fail = 0
    for r in await remind_candidates():
        uid = r["user_id"]
        try:
            await send_reminder(bot, uid, r["first_name"], r["balance"])
            ok += 1
        except TelegramForbiddenError:
            await mark_blocked(uid)
            fail += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            fail += 1
        except Exception:
            fail += 1
        await mark_reminded(uid)
        await asyncio.sleep(0.05)
    return ok, fail


async def remind_loop(bot: Bot):
    while True:
        await _sleep_until(REMIND_HOUR_MSK)
        try:
            res = await run_reminders(bot)
            if res:
                await _tell_admins(
                    bot, f"🔔 Напоминание неактивным отправлено.\n"
                         f"Доставлено: {res[0]}, не доставлено: {res[1]}")
        except Exception:
            logging.exception("remind loop error")


# ---------- отчёт админу ----------

def _money(p):
    return f"{p[0]} шт. на {fmt(p[1])} ⭐"


async def report_text(start, end, title):
    s = await report_stats(start, end)
    by = ", ".join(f"{n} {c}" for n, c in s["by_sponsor"]) or "—"
    lines = [
        f"📊 Отчёт {title}", "",
        f"👥 Новых: {s['new']} (всего {s['users']})",
        f"📋 Заданий: {s['tasks']} ({by})",
        f"❌ Из них отписалось: {s['unsub']}", "",
        f"💸 Заявки: создано {_money(s['created'])}, "
        f"выплачено {_money(s['paid'])}",
        f"⏳ Ждут выплаты: {_money(s['pending'])}",
        f"💰 Баланс пользователей: {s['balance']:.2f} ⭐", "",
        "🤝 Сервисы:",
    ]
    for sp in await get_sponsors(only_active=True):
        name = sp["name"]
        if name not in sponsors.FETCHERS:
            continue
        f_ = sponsors.fails.get(name, 0)
        e_ = sponsors.empties.get(name, 0)
        if f_ >= 1:
            lines.append(f"⚠️ {name}: ошибок подряд {f_}")
        elif e_ >= 10:
            lines.append(f"⚠️ {name}: без заданий {e_} раз подряд")
        else:
            lines.append(f"✅ {name}")
    return "\n".join(lines)


async def report_loop(bot: Bot):
    """Каждое утро в REPORT_HOUR_MSK: итоги вчерашнего дня."""
    while True:
        await _sleep_until(REPORT_HOUR_MSK)
        try:
            if await get_setting("report_enabled") != "1":
                continue
            day = datetime.now(MSK) - timedelta(days=1)
            text = await report_text(
                day_start(1), day_start(0), f"за {day:%d.%m}")
            await _tell_admins(bot, text)
        except Exception:
            logging.exception("report loop error")


# ---------- админка: ежедневное уведомление ----------

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


@router.callback_query(F.data == "daily:col")
async def daily_col(call: CallbackQuery):
    await safe_edit(call, "У какой кнопки поменять цвет?", InlineKeyboardMarkup(
        inline_keyboard=[
            [b("Пригласить друга", "daily:cw:ref")],
            [b("Выполнить задания", "daily:cw:tasks")],
            [b("⬅️ Назад", "adm:daily")],
        ]))
    await call.answer()


@router.callback_query(F.data.startswith("daily:cw:"))
async def daily_col_which(call: CallbackQuery):
    which = call.data.split(":")[2]
    await safe_edit(call, "Выбери цвет:",
                    color_kb(f"daily:sc:{which}", "daily:col"))
    await call.answer()


@router.callback_query(F.data.startswith("daily:sc:"))
async def daily_col_set(call: CallbackQuery, state: FSMContext, bot: Bot):
    _, _, which, col = call.data.split(":")
    if which not in ("ref", "tasks"):
        await call.answer()
        return
    await set_setting(f"daily_style_{which}", col if col in STYLES else "")
    await call.answer("Цвет сохранён")
    await daily_menu(call, state, bot)


@router.callback_query(F.data == "daily:test")
async def daily_test(call: CallbackQuery, bot: Bot):
    await send_post(bot, call.message.chat.id,
                    await build_daily_post(), await daily_markup())
    await call.answer("Отправил тебе")


# ---------- админка: напоминания и отчёт ----------

async def _rem_summary():
    on = await get_setting("remind_enabled") == "1"
    rp = await get_setting("report_enabled") == "1"
    text = (
        "🔔 Напоминания\n\n"
        f"👋 Неактивным: {'включено' if on else 'выключено'}\n"
        f"Раз в 5 дней, в {REMIND_HOUR_MSK}:00 по Москве, тем, кто "
        "3 и более дня не заходил.\n"
        "В тексте работают {name}, {balance}, {reward}.\n\n"
        f"📊 Отчёт тебе: {'включён' if rp else 'выключен'}, "
        f"каждое утро в {REPORT_HOUR_MSK}:00 по Москве.")
    return text, on, rp


@router.callback_query(F.data == "adm:rem")
async def rem_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, on, rp = await _rem_summary()
    await safe_edit(call, text, rem_kb(on, rp))
    await call.answer()


@router.callback_query(F.data == "rem:tg")
async def rem_toggle(call: CallbackQuery, state: FSMContext):
    on = await get_setting("remind_enabled") == "1"
    await set_setting("remind_enabled", "0" if on else "1")
    await rem_menu(call, state)


@router.callback_query(F.data == "rem:rp")
async def rep_toggle(call: CallbackQuery, state: FSMContext):
    on = await get_setting("report_enabled") == "1"
    await set_setting("report_enabled", "0" if on else "1")
    await rem_menu(call, state)


@router.callback_query(F.data == "rem:t1")
@router.callback_query(F.data == "rem:t0")
async def rem_text_ask(call: CallbackQuery, state: FSMContext):
    zero = call.data.endswith("t0")
    await state.set_state(RemForm.t0 if zero else RemForm.t1)
    who = "у кого баланс 0" if zero else "у кого есть баланс"
    await call.message.answer(
        f"Отправь новый текст напоминания для тех, {who}.\n"
        "Можно {name}, {balance}, {reward}. Жирный шрифт и премиум-эмодзи "
        "сохранятся.", reply_markup=back_kb("adm:rem"))
    await call.answer()


async def _rem_text_save(message: Message, state: FSMContext, key):
    if not message.text:
        await message.answer("Нужен именно текст.")
        return
    await set_setting(key, message.html_text)
    await state.clear()
    text, on, rp = await _rem_summary()
    await message.answer("✅ Текст сохранён\n\n" + text,
                         reply_markup=rem_kb(on, rp))


@router.message(RemForm.t1)
async def rem_text_t1(message: Message, state: FSMContext):
    await _rem_text_save(message, state, "remind_text")


@router.message(RemForm.t0)
async def rem_text_t0(message: Message, state: FSMContext):
    await _rem_text_save(message, state, "remind_text_zero")


@router.callback_query(F.data == "rem:col")
async def rem_col(call: CallbackQuery):
    await safe_edit(call, "Цвет кнопки «Выполнить задания» в напоминании:",
                    color_kb("rem:sc", "adm:rem"))
    await call.answer()


@router.callback_query(F.data.startswith("rem:sc:"))
async def rem_col_set(call: CallbackQuery, state: FSMContext):
    col = call.data.split(":")[2]
    await set_setting("remind_style", col if col in STYLES else "")
    await call.answer("Цвет сохранён")
    await rem_menu(call, state)


@router.callback_query(F.data == "rem:test")
async def rem_test(call: CallbackQuery, bot: Bot):
    name = call.from_user.first_name
    await send_reminder(bot, call.message.chat.id, name, 12.5)
    await send_reminder(bot, call.message.chat.id, name, 0)
    await call.answer("Отправил два варианта")


@router.callback_query(F.data == "rem:now")
async def rem_report_now(call: CallbackQuery):
    now = int(datetime.now(MSK).timestamp())
    await call.message.answer(await report_text(day_start(0), now,
                                                 "за сегодня (пока)"))
    await call.answer()
