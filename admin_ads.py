import asyncio
import json

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import builder
from ads import ad_to_post, safe_edit, send_post
from config import ADMIN_IDS
from daily import broadcast
from database import (
    GROUPS, ad_stats, add_ad, delete_ad, get_ad, list_ads, toggle_ad,
    update_ad, user_ids_by_group,
)
from keyboards import ad_delete_kb, ad_menu_kb, ads_kb, bc_groups_kb

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

_tasks = set()


# ---------- список показов ----------

@router.callback_query(F.data == "adm:ads")
async def ads_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    ads = await list_ads()
    if ads:
        text = ("📣 Показы\n\nПоказываются по кругу: 1, 2, 3, снова 1.\n"
                "✅ включён, ❌ выключен")
    else:
        text = "📣 Показов пока нет."
    await safe_edit(call, text, ads_kb(ads))
    await call.answer()


async def _ad_text(ad):
    s = await ad_stats(ad["id"])
    return (
        f"Показ #{ad['id']}: {'включён' if ad['enabled'] else 'выключен'}\n"
        f"Показан: всего {s['total']}, сегодня {s['today']}, "
        f"за 7 дней {s['week']}\n"
        "(нажатия на ссылки Telegram боту не сообщает)")


# ---------- создание и изменение (через конструктор) ----------

@router.callback_query(F.data == "ad:new")
async def ad_new(call: CallbackQuery, state: FSMContext):
    await builder.start(call, state, "ad")
    await call.answer()


async def ad_done(call, state, bot, draft, ctx):
    await add_ad(draft)
    await call.answer("Сохранено ✅")
    await ads_menu(call, state)


async def adedit_done(call, state, bot, draft, ctx):
    ad_id = int(ctx.split(":")[1])
    await update_ad(
        ad_id, kind=draft["kind"], file_id=draft["file_id"],
        text=draft["text"],
        entities=json.dumps(draft["entities"], ensure_ascii=False),
        buttons=json.dumps(draft["buttons"], ensure_ascii=False),
        sticker=draft["sticker"])
    await call.answer("Сохранено ✅")
    await ads_menu(call, state)


@router.callback_query(F.data.startswith("ad:edit:"))
async def ad_edit(call: CallbackQuery, state: FSMContext):
    ad_id = int(call.data.split(":")[2])
    ad = await get_ad(ad_id)
    if not ad:
        await call.answer("Показ не найден", show_alert=True)
        return
    await builder.start(call, state, f"adedit:{ad_id}",
                        builder.draft_from_post(ad_to_post(ad)))
    await call.answer()


# ---------- просмотр, включение, удаление ----------

@router.callback_query(F.data.startswith("ad:open:"))
async def ad_open(call: CallbackQuery, bot: Bot):
    ad = await get_ad(int(call.data.split(":")[2]))
    if not ad:
        await call.answer("Показ не найден", show_alert=True)
        return
    await call.message.answer("👀 Так это видят пользователи:")
    try:
        await send_post(bot, call.message.chat.id, ad_to_post(ad))
    except Exception as e:
        await call.message.answer(f"Не получилось показать: {e}")
    await call.message.answer(await _ad_text(ad), reply_markup=ad_menu_kb(ad))
    await call.answer()


@router.callback_query(F.data.startswith("ad:tg:"))
async def ad_toggle(call: CallbackQuery):
    ad_id = int(call.data.split(":")[2])
    await toggle_ad(ad_id)
    ad = await get_ad(ad_id)
    await safe_edit(call, await _ad_text(ad), ad_menu_kb(ad))
    await call.answer()


@router.callback_query(F.data.startswith("ad:del:"))
async def ad_delete(call: CallbackQuery):
    ad_id = int(call.data.split(":")[2])
    await safe_edit(call, f"Удалить показ #{ad_id}?", ad_delete_kb(ad_id))
    await call.answer()


@router.callback_query(F.data.startswith("ad:delok:"))
async def ad_delete_ok(call: CallbackQuery, state: FSMContext):
    await delete_ad(int(call.data.split(":")[2]))
    await call.answer("Удалено")
    await ads_menu(call, state)


# ---------- рассылка всем (через конструктор) ----------

@router.callback_query(F.data == "adm:bc")
async def bc_start(call: CallbackQuery, state: FSMContext):
    await builder.start(call, state, "bc")
    await call.answer()


async def bc_done(call, state, bot, draft, ctx):
    counts = {}
    for g in GROUPS:
        counts[g] = len(await user_ids_by_group(g))
    await call.message.answer("Кому отправить?",
                              reply_markup=bc_groups_kb(counts))
    await call.answer()


async def _run(bot: Bot, chat_id, post, ids):
    ok, fail = await broadcast(bot, post, ids=ids)
    await bot.send_message(
        chat_id,
        f"✅ Рассылка завершена\nДоставлено: {ok}\nНе доставлено: {fail}")


@router.callback_query(F.data.startswith("bcg:"))
async def bc_go(call: CallbackQuery, state: FSMContext, bot: Bot):
    group = call.data.split(":")[1]
    post = (await state.get_data()).get("draft")
    if not post or group not in GROUPS:
        await call.answer("Нечего отправлять", show_alert=True)
        return
    ids = await user_ids_by_group(group)
    await state.clear()
    await safe_edit(
        call, f"🚀 Рассылка запущена ({len(ids)} получателей), "
              "пришлю итог.")
    task = asyncio.create_task(_run(bot, call.message.chat.id, post, ids))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    await call.answer()


builder.register_done("ad", ad_done)
builder.register_done("adedit", adedit_done)
builder.register_done("bc", bc_done)
