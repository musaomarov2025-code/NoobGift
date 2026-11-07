import asyncio

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import json

from ads import (
    ad_to_post, parse_buttons, post_from_message, safe_edit, send_post,
)
from config import ADMIN_IDS
from daily import broadcast
from database import (
    GROUPS, ad_stats, add_ad, delete_ad, get_ad, list_ads, toggle_ad,
    update_ad, user_ids_by_group,
)
from keyboards import (
    ad_delete_kb, ad_menu_kb, ad_save_kb, ads_kb, back_kb, bc_groups_kb,
)

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

_tasks = set()

POST_HINT = (
    "Отправь пост одним сообщением: текст или фото/видео/гиф с подписью.\n"
    "Жирный шрифт, курсив и премиум-эмодзи сохранятся как есть.")
BTN_HINT = (
    "Отправь кнопки, каждая строка это ряд:\n"
    "Текст - ссылка\n"
    "Несколько кнопок в ряд: Текст - ссылка | Текст - ссылка\n\n"
    "Если кнопки не нужны, отправь «-».")


class AdForm(StatesGroup):
    post = State()
    buttons = State()
    edit_post = State()
    edit_buttons = State()


class BcForm(StatesGroup):
    post = State()
    buttons = State()
    sticker = State()


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


# ---------- создание ----------

@router.callback_query(F.data == "ad:new")
async def ad_new(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdForm.post)
    await safe_edit(call, "➕ Новый показ\n\n" + POST_HINT,
                    back_kb("adm:ads"))
    await call.answer()


@router.message(AdForm.post)
async def ad_post(message: Message, state: FSMContext):
    post = post_from_message(message)
    if not post:
        await message.answer("Нужен текст, фото, видео или гиф.")
        return
    await state.update_data(post=post)
    await state.set_state(AdForm.buttons)
    await message.answer(BTN_HINT, reply_markup=back_kb("adm:ads"))


@router.message(AdForm.buttons)
async def ad_buttons(message: Message, state: FSMContext, bot: Bot):
    txt = (message.text or "").strip()
    buttons = [] if txt == "-" else parse_buttons(txt)
    if buttons is None:
        await message.answer("Не понял кнопки. Формат: Текст - ссылка")
        return
    post = (await state.get_data())["post"]
    post["buttons"] = buttons
    await state.update_data(post=post)
    await message.answer("👀 Так это увидят пользователи:")
    try:
        await send_post(bot, message.chat.id, post)
    except Exception as e:
        await message.answer(f"Не получилось показать: {e}\n"
                             "Проверь ссылки в кнопках и отправь снова.")
        return
    await message.answer("Сохранить показ?", reply_markup=ad_save_kb())


@router.callback_query(F.data == "ad:save")
async def ad_save(call: CallbackQuery, state: FSMContext):
    post = (await state.get_data()).get("post")
    if not post:
        await call.answer("Нечего сохранять", show_alert=True)
        return
    await add_ad(post)
    await call.answer("Сохранено ✅")
    await ads_menu(call, state)


# ---------- просмотр и изменение ----------

async def _ad_text(ad):
    s = await ad_stats(ad["id"])
    return (
        f"Показ #{ad['id']}: {'включён' if ad['enabled'] else 'выключен'}\n"
        f"Показан: всего {s['total']}, сегодня {s['today']}, "
        f"за 7 дней {s['week']}\n"
        "(нажатия на ссылки Telegram боту не сообщает)")


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


@router.callback_query(F.data.startswith("ad:ep:"))
async def ad_edit_post(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdForm.edit_post)
    await state.update_data(ad_id=int(call.data.split(":")[2]))
    await call.message.answer("✏️ Новый пост.\n\n" + POST_HINT,
                              reply_markup=back_kb("adm:ads"))
    await call.answer()


@router.message(AdForm.edit_post)
async def ad_edit_post_save(message: Message, state: FSMContext, bot: Bot):
    post = post_from_message(message)
    if not post:
        await message.answer("Нужен текст, фото, видео или гиф.")
        return
    ad_id = (await state.get_data())["ad_id"]
    await update_ad(
        ad_id, kind=post["kind"], file_id=post["file_id"],
        text=post["text"],
        entities=json.dumps(post["entities"], ensure_ascii=False))
    await state.clear()
    ad = await get_ad(ad_id)
    await message.answer("✅ Пост обновлён. Так он выглядит:")
    await send_post(bot, message.chat.id, ad_to_post(ad))
    await message.answer(await _ad_text(ad), reply_markup=ad_menu_kb(ad))


@router.callback_query(F.data.startswith("ad:eb:"))
async def ad_edit_buttons(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdForm.edit_buttons)
    await state.update_data(ad_id=int(call.data.split(":")[2]))
    await call.message.answer("🔘 Новые кнопки.\n\n" + BTN_HINT,
                              reply_markup=back_kb("adm:ads"))
    await call.answer()


@router.message(AdForm.edit_buttons)
async def ad_edit_buttons_save(message: Message, state: FSMContext,
                               bot: Bot):
    txt = (message.text or "").strip()
    buttons = [] if txt == "-" else parse_buttons(txt)
    if buttons is None:
        await message.answer("Не понял кнопки. Формат: Текст - ссылка")
        return
    ad_id = (await state.get_data())["ad_id"]
    await update_ad(
        ad_id, buttons=json.dumps(buttons, ensure_ascii=False))
    await state.clear()
    ad = await get_ad(ad_id)
    await message.answer("✅ Кнопки обновлены. Так выглядит показ:")
    try:
        await send_post(bot, message.chat.id, ad_to_post(ad))
    except Exception as e:
        await message.answer(f"Не получилось показать: {e}")
    await message.answer(await _ad_text(ad), reply_markup=ad_menu_kb(ad))


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


# ---------- рассылка всем ----------

@router.callback_query(F.data == "adm:bc")
async def bc_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BcForm.post)
    await safe_edit(call, "📨 Рассылка всем пользователям\n\n" + POST_HINT,
                    back_kb("adm:back"))
    await call.answer()


@router.message(BcForm.post)
async def bc_post(message: Message, state: FSMContext):
    post = post_from_message(message)
    if not post:
        await message.answer("Нужен текст, фото, видео или гиф.")
        return
    await state.update_data(post=post)
    await state.set_state(BcForm.buttons)
    await message.answer(BTN_HINT, reply_markup=back_kb("adm:back"))


@router.message(BcForm.buttons)
async def bc_buttons(message: Message, state: FSMContext, bot: Bot):
    txt = (message.text or "").strip()
    buttons = [] if txt == "-" else parse_buttons(txt)
    if buttons is None:
        await message.answer("Не понял кнопки. Формат: Текст - ссылка")
        return
    post = (await state.get_data())["post"]
    post["buttons"] = buttons
    await state.update_data(post=post)
    await message.answer("👀 Так увидят пользователи:")
    try:
        await send_post(bot, message.chat.id, post)
    except Exception as e:
        await message.answer(f"Не получилось показать: {e}\n"
                             "Проверь ссылки в кнопках и отправь снова.")
        return
    await state.set_state(BcForm.sticker)
    await message.answer(
        "Добавить стикер перед постом? Отправь стикер "
        "или «-», если не нужно.", reply_markup=back_kb("adm:back"))


@router.message(BcForm.sticker)
async def bc_sticker(message: Message, state: FSMContext):
    if message.sticker:
        post = (await state.get_data())["post"]
        post["sticker"] = message.sticker.file_id
        await state.update_data(post=post)
    elif (message.text or "").strip() != "-":
        await message.answer("Отправь стикер или «-».")
        return
    counts = {}
    for g in GROUPS:
        counts[g] = len(await user_ids_by_group(g))
    await message.answer("Кому отправить?", reply_markup=bc_groups_kb(counts))


async def _run(bot: Bot, chat_id, post, ids):
    ok, fail = await broadcast(bot, post, ids=ids)
    await bot.send_message(
        chat_id,
        f"✅ Рассылка завершена\nДоставлено: {ok}\nНе доставлено: {fail}")


@router.callback_query(F.data.startswith("bcg:"))
async def bc_go(call: CallbackQuery, state: FSMContext, bot: Bot):
    group = call.data.split(":")[1]
    post = (await state.get_data()).get("post")
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
