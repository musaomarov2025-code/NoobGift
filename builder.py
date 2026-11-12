"""Конструктор поста: текст, медиа, стикер и кнопки (с цветами) по
отдельности, с предпросмотром. Им пользуются рассылка и показы."""
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ads import STYLES, post_from_message, safe_edit, send_post
from config import ADMIN_IDS
from keyboards import admin_kb, b, back_kb, color_kb, ik

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

DONE = {}   # префикс контекста -> async fn(call, state, bot, draft, ctx)
COLORS = {"": "⚪", "primary": "🔵", "success": "🟢", "danger": "🔴"}
URL_RE = re.compile(r"^(https?://|t\.me/|tg://)\S+$")
MAX_IN_ROW = 3


class BForm(StatesGroup):
    text = State()
    media = State()
    sticker = State()
    b_text = State()
    b_link = State()


def register_done(prefix, fn):
    DONE[prefix] = fn


# ---------- черновик (чистые функции) ----------

def empty_draft():
    return {"kind": "text", "file_id": None, "text": "", "entities": [],
            "buttons": [], "sticker": None}


def draft_from_post(post):
    d = empty_draft()
    for k in d:
        if post.get(k) is not None:
            d[k] = post[k]
    d["buttons"] = [list(row) for row in d["buttons"]]
    return d


def draft_ok(d):
    return bool(d["text"] or d["file_id"] or d["sticker"])


def flat_buttons(d):
    return [(i, j) for i, row in enumerate(d["buttons"])
            for j in range(len(row))]


def add_button(d, btn, new_row):
    rows = d["buttons"]
    if new_row or not rows or len(rows[-1]) >= MAX_IN_ROW:
        rows.append([btn])
    else:
        rows[-1].append(btn)


def remove_button(d, flat_idx):
    pos = flat_buttons(d)
    if not 0 <= flat_idx < len(pos):
        return False
    i, j = pos[flat_idx]
    d["buttons"][i].pop(j)
    if not d["buttons"][i]:
        d["buttons"].pop(i)
    return True


def describe_buttons(d):
    lines = []
    for row in d["buttons"]:
        for x in row:
            mark = COLORS.get(x.get("style") or "", "⚪")
            lines.append(f"{len(lines) + 1}. {mark} {x['text']}")
    return lines


def summary(d, ctx):
    kind = ctx.split(":")[0]
    title = {"bc": "Рассылка", "ad": "Новый показ",
             "adedit": f"Показ #{ctx.split(':')[-1]}"}.get(kind, "Пост")
    media = {"photo": "фото", "video": "видео",
             "animation": "гиф"}.get(d["kind"], "нет")
    n = len(d["text"])
    text_line = f"есть ({n} симв.)" if n else "нет"
    return (
        f"🧩 Конструктор: {title}\n\n"
        f"✏️ Текст: {text_line}\n"
        f"🖼 Медиа: {media}\n"
        f"😀 Стикер: {'есть' if d['sticker'] else 'нет'}\n"
        f"🔘 Кнопки: {len(flat_buttons(d))}\n\n"
        "Нажми «Предпросмотр», чтобы увидеть, как это выглядит у людей.")


def menu_kb(ctx):
    kind = ctx.split(":")[0]
    done = {"bc": "➡️ Выбрать получателей", "ad": "💾 Сохранить показ",
            "adedit": "💾 Сохранить изменения"}.get(kind, "✅ Готово")
    return ik([
        [b("✏️ Текст", "bld:text"), b("🖼 Медиа", "bld:media")],
        [b("😀 Стикер", "bld:stk"), b("🔘 Кнопки", "bld:btn")],
        [b("👀 Предпросмотр", "bld:prev")],
        [b(done, "bld:done", "success")],
        [b("❌ Отмена", "bld:cancel", "danger")],
    ])


# ---------- вход и показ меню ----------

async def _get(state):
    data = await state.get_data()
    return data["draft"], data["ctx"]


async def render(event, state, new=False):
    d, ctx = await _get(state)
    text, kb = summary(d, ctx), menu_kb(ctx)
    if isinstance(event, CallbackQuery) and not new:
        await safe_edit(event, text, kb)
    else:
        msg = event.message if isinstance(event, CallbackQuery) else event
        await msg.answer(text, reply_markup=kb)


async def start(event, state, ctx, draft=None):
    """Открыть конструктор. ctx: bc, ad или adedit:<id>."""
    await state.clear()
    await state.update_data(draft=draft or empty_draft(), ctx=ctx)
    await render(event, state)


@router.callback_query(F.data == "bld:menu")
async def to_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await render(call, state)
    await call.answer()


@router.callback_query(F.data == "bld:cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(call, "🛠 Админ-панель", admin_kb())
    await call.answer()


# ---------- текст, медиа, стикер ----------

@router.callback_query(F.data == "bld:text")
async def ask_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BForm.text)
    await call.message.answer(
        "✏️ Отправь текст поста одним сообщением. Жирный шрифт, курсив и "
        "премиум-эмодзи сохранятся.\n"
        "Если пришлёшь фото или видео с подписью, возьму и текст, и медиа.",
        reply_markup=back_kb("bld:menu"))
    await call.answer()


@router.message(BForm.text)
async def got_text(message: Message, state: FSMContext):
    post = post_from_message(message)
    if not post:
        await message.answer("Нужен текст (можно с фото, видео или гиф).")
        return
    d, _ = await _get(state)
    if post["kind"] == "sticker":
        d["sticker"] = post["file_id"]
    else:
        d["text"] = post["text"]
        d["entities"] = post["entities"]
        if post["kind"] != "text":
            d["kind"], d["file_id"] = post["kind"], post["file_id"]
    await state.update_data(draft=d)
    await state.set_state(None)
    await render(message, state)


@router.callback_query(F.data == "bld:media")
async def ask_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BForm.media)
    await call.message.answer(
        "🖼 Отправь фото, видео или гиф. Текст останется.\n"
        "Отправь «-», чтобы убрать медиа.",
        reply_markup=back_kb("bld:menu"))
    await call.answer()


@router.message(BForm.media)
async def got_media(message: Message, state: FSMContext):
    d, _ = await _get(state)
    if (message.text or "").strip() == "-":
        d["kind"], d["file_id"] = "text", None
    else:
        post = post_from_message(message)
        if not post or post["kind"] not in ("photo", "video", "animation"):
            await message.answer("Нужно фото, видео или гиф, либо «-».")
            return
        d["kind"], d["file_id"] = post["kind"], post["file_id"]
    await state.update_data(draft=d)
    await state.set_state(None)
    await render(message, state)


@router.callback_query(F.data == "bld:stk")
async def ask_sticker(call: CallbackQuery, state: FSMContext):
    await state.set_state(BForm.sticker)
    await call.message.answer(
        "😀 Отправь стикер, он придёт перед постом.\n"
        "Отправь «-», чтобы убрать стикер.",
        reply_markup=back_kb("bld:menu"))
    await call.answer()


@router.message(BForm.sticker)
async def got_sticker(message: Message, state: FSMContext):
    d, _ = await _get(state)
    if message.sticker:
        d["sticker"] = message.sticker.file_id
    elif (message.text or "").strip() == "-":
        d["sticker"] = None
    else:
        await message.answer("Нужен стикер или «-».")
        return
    await state.update_data(draft=d)
    await state.set_state(None)
    await render(message, state)


# ---------- кнопки ----------

async def show_buttons(event, state, new=False):
    d, _ = await _get(state)
    lines = describe_buttons(d)
    text = "🔘 Кнопки\n\n" + (
        "\n".join(lines) if lines else "Кнопок пока нет.")
    rows = [[b("➕ Добавить кнопку", "bld:badd")]]
    for n, line in enumerate(lines):
        rows.append([b(f"🗑 {line}", f"bld:bdel:{n}")])
    if lines:
        rows.append([b("🧹 Убрать все", "bld:bclr")])
    rows.append([b("⬅️ К конструктору", "bld:menu")])
    kb = ik(rows)
    if isinstance(event, CallbackQuery) and not new:
        await safe_edit(event, text, kb)
    else:
        msg = event.message if isinstance(event, CallbackQuery) else event
        await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "bld:btn")
async def buttons_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(None)
    await show_buttons(call, state)
    await call.answer()


@router.callback_query(F.data == "bld:badd")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(BForm.b_text)
    await call.message.answer("Название кнопки (до 40 символов):",
                              reply_markup=back_kb("bld:btn"))
    await call.answer()


@router.message(BForm.b_text)
async def add_text(message: Message, state: FSMContext):
    t = (message.text or "").strip()
    if not t or len(t) > 40:
        await message.answer("Нужно от 1 до 40 символов.")
        return
    await state.update_data(b_tmp={"text": t})
    await state.set_state(BForm.b_link)
    await message.answer("Ссылка кнопки (https://… или t.me/…):",
                         reply_markup=back_kb("bld:btn"))


@router.message(BForm.b_link)
async def add_link(message: Message, state: FSMContext):
    url = (message.text or "").strip()
    if not URL_RE.match(url):
        await message.answer("Не похоже на ссылку. Пример: https://t.me/name")
        return
    if url.startswith("t.me/"):
        url = "https://" + url
    tmp = (await state.get_data()).get("b_tmp") or {}
    tmp["url"] = url
    await state.update_data(b_tmp=tmp)
    await state.set_state(None)
    await message.answer("Выбери цвет кнопки:",
                         reply_markup=color_kb("bld:col", "bld:btn"))


async def _finish_button(call, state, new_row):
    data = await state.get_data()
    tmp, d = data.get("b_tmp"), data["draft"]
    if not tmp or "url" not in tmp:
        await call.answer("Начни добавление заново", show_alert=True)
        return
    add_button(d, {"text": tmp["text"], "url": tmp["url"],
                   "style": tmp.get("style", "")}, new_row)
    await state.update_data(draft=d, b_tmp=None)
    await show_buttons(call, state)
    await call.answer("Кнопка добавлена")


@router.callback_query(F.data.startswith("bld:col:"))
async def pick_color(call: CallbackQuery, state: FSMContext):
    col = call.data.split(":")[2]
    style = col if col in STYLES else ""
    data = await state.get_data()
    tmp = data.get("b_tmp")
    if not tmp or "url" not in tmp:
        await call.answer("Начни добавление заново", show_alert=True)
        return
    tmp["style"] = style
    await state.update_data(b_tmp=tmp)
    if not data["draft"]["buttons"]:
        await _finish_button(call, state, True)
        return
    await safe_edit(call, "Куда поставить кнопку?", ik([
        [b("⬇️ Новая строка", "bld:pl:new")],
        [b("➡️ Рядом с предыдущей", "bld:pl:same")],
    ]))
    await call.answer()


@router.callback_query(F.data.startswith("bld:pl:"))
async def place_button(call: CallbackQuery, state: FSMContext):
    await _finish_button(call, state, call.data.split(":")[2] == "new")


@router.callback_query(F.data.startswith("bld:bdel:"))
async def del_button(call: CallbackQuery, state: FSMContext):
    d, _ = await _get(state)
    remove_button(d, int(call.data.split(":")[2]))
    await state.update_data(draft=d)
    await show_buttons(call, state)
    await call.answer("Удалено")


@router.callback_query(F.data == "bld:bclr")
async def clear_buttons(call: CallbackQuery, state: FSMContext):
    d, _ = await _get(state)
    d["buttons"] = []
    await state.update_data(draft=d)
    await show_buttons(call, state)
    await call.answer("Кнопки убраны")


# ---------- предпросмотр и завершение ----------

@router.callback_query(F.data == "bld:prev")
async def preview(call: CallbackQuery, state: FSMContext, bot: Bot):
    d, _ = await _get(state)
    if not draft_ok(d):
        await call.answer("Пост пока пустой", show_alert=True)
        return
    await call.answer()
    await call.message.answer("👀 Так это увидят люди:")
    try:
        await send_post(bot, call.message.chat.id, d)
    except Exception as e:
        await call.message.answer(
            f"Не получилось показать: {e}\nПроверь текст и ссылки кнопок.")
    await render(call, state, new=True)


@router.callback_query(F.data == "bld:done")
async def done(call: CallbackQuery, state: FSMContext, bot: Bot):
    d, ctx = await _get(state)
    if not draft_ok(d):
        await call.answer("Пост пустой: добавь текст, медиа или стикер",
                          show_alert=True)
        return
    fn = DONE.get(ctx.split(":")[0])
    if not fn:
        await call.answer("Неизвестное действие", show_alert=True)
        return
    await fn(call, state, bot, d, ctx)
