"""Источники трафика и статистика для рекламодателей (/stat_имя)."""
import re
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ads import safe_edit
from config import ADMIN_IDS, MSK
from database import (
    create_source, delete_source, get_source, list_sources, source_stats,
)
from keyboards import (
    back_kb, source_del_kb, source_kb, sources_kb, stat_kb,
)

NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,24}$")
OWNER_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
STAT_RE = re.compile(r"^/stat_([A-Za-z0-9_]{2,24})(?:@\w+)?\s*$")

admin_router = Router()
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))
admin_router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

public_router = Router()


class SrcForm(StatesGroup):
    name = State()
    owner = State()


async def source_text(bot: Bot, row):
    s = await source_stats(row["name"])
    me = await bot.me()
    counted = s["tasks_total"] - s["unsub"]
    return (
        f"📈 Источник: {row['name']}\n\n"
        f"👥 Пришло: всего {s['users']}, сегодня {s['new_today']}, "
        f"за 7 дней {s['new_week']}\n"
        f"✅ Заданий выполнено: всего {s['tasks_total']}, "
        f"сегодня {s['tasks_today']}\n"
        f"❌ Отписалось: {s['unsub']}\n"
        f"💎 Засчитано: {counted}\n\n"
        f"🔗 Ссылка: https://t.me/{me.username}?start={row['name']}\n"
        f"👤 Владелец: @{row['owner']}\n\n"
        f"Обновлено: {datetime.now(MSK):%H:%M} МСК"
    )


def allowed(user, row):
    if user.id in ADMIN_IDS:
        return True
    return bool(user.username
                and user.username.lower() == row["owner"].lower())


# ---------- для рекламодателей ----------

@public_router.message(F.text.startswith("/stat_"))
async def stat_cmd(message: Message, bot: Bot):
    m = STAT_RE.match(message.text or "")
    if not m:
        return
    row = await get_source(m.group(1))
    if not row:
        await message.answer("Источник не найден.")
        return
    if not allowed(message.from_user, row):
        await message.answer("Нет доступа к этой статистике.")
        return
    await message.answer(await source_text(bot, row),
                         reply_markup=stat_kb(row["name"]))


@public_router.callback_query(F.data.startswith("srcupd:"))
async def stat_update(call: CallbackQuery, bot: Bot):
    row = await get_source(call.data.split(":", 1)[1])
    if not row or not allowed(call.from_user, row):
        await call.answer("Нет доступа", show_alert=True)
        return
    await safe_edit(call, await source_text(bot, row),
                    stat_kb(row["name"]))
    await call.answer("Обновлено")


# ---------- админка ----------

@admin_router.callback_query(F.data == "adm:src")
async def src_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = await list_sources()
    text = ("📈 Источники трафика\n\nУ каждого своя ссылка и статистика "
            "/stat_имя для владельца." if rows
            else "📈 Источников пока нет.")
    await safe_edit(call, text, sources_kb(rows))
    await call.answer()


@admin_router.callback_query(F.data == "src:new")
async def src_new(call: CallbackQuery, state: FSMContext):
    await state.set_state(SrcForm.name)
    await safe_edit(
        call,
        "Отправь имя источника на английском (буквы, цифры, _), "
        "например kanal1. По нему будет ссылка и команда /stat_kanal1.",
        back_kb("adm:src"))
    await call.answer()


@admin_router.message(SrcForm.name)
async def src_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not NAME_RE.match(name):
        await message.answer("Нужно 2–24 символа: английские буквы, "
                             "цифры и _. Попробуй ещё раз.")
        return
    if await get_source(name):
        await message.answer("Такой источник уже есть, придумай другое имя.")
        return
    await state.update_data(name=name.lower())
    await state.set_state(SrcForm.owner)
    await message.answer("Отправь @юзернейм владельца ссылки.",
                         reply_markup=back_kb("adm:src"))


@admin_router.message(SrcForm.owner)
async def src_owner(message: Message, state: FSMContext, bot: Bot):
    owner = (message.text or "").strip().lstrip("@")
    if not OWNER_RE.match(owner):
        await message.answer("Не похоже на юзернейм. Пример: @ivan_ivanov")
        return
    name = (await state.get_data())["name"]
    await create_source(name, owner)
    await state.clear()
    row = await get_source(name)
    await message.answer(await source_text(bot, row),
                         reply_markup=source_kb(name))


@admin_router.callback_query(F.data.startswith("src:open:"))
async def src_open(call: CallbackQuery, bot: Bot):
    row = await get_source(call.data.split(":", 2)[2])
    if not row:
        await call.answer("Источник не найден", show_alert=True)
        return
    await safe_edit(call, await source_text(bot, row),
                    source_kb(row["name"]))
    await call.answer()


@admin_router.callback_query(F.data.startswith("src:del:"))
async def src_del(call: CallbackQuery):
    name = call.data.split(":", 2)[2]
    await safe_edit(
        call, f"Удалить источник {name}? Ссылка перестанет считаться, "
              "статистика пропадёт.", source_del_kb(name))
    await call.answer()


@admin_router.callback_query(F.data.startswith("src:delok:"))
async def src_del_ok(call: CallbackQuery, state: FSMContext):
    await delete_source(call.data.split(":", 2)[2])
    await call.answer("Удалено")
    await src_menu(call, state)
