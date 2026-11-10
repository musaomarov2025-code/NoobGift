import json
import logging
import re
import uuid

import aiohttp

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions,
    MessageEntity,
)

from database import count_ad_show, get_sponsor, next_ad

LINE_RE = re.compile(r"^(.+?)\s+[-—–]\s+((?:https?://|t\.me/|tg://)\S+)$")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def parse_buttons(text):
    """Строки вида «Текст - ссылка»; несколько в ряд через « | ».
    Возвращает список рядов или None, если формат неверный."""
    rows = []
    for line in text.strip().splitlines():
        row = []
        for part in line.split("|"):
            part = part.strip()
            if not part:
                continue
            m = LINE_RE.match(part)
            if not m:
                return None
            url = m.group(2)
            if url.startswith("t.me/"):
                url = "https://" + url
            row.append({"text": m.group(1).strip(), "url": url})
        if row:
            rows.append(row)
    return rows


def buttons_markup(buttons):
    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=x["text"], url=x["url"]) for x in row]
        for row in buttons
    ])


def post_from_message(m):
    """Превращает сообщение админа в пост (форматирование сохраняется)."""
    if m.photo:
        kind, fid, text, ents = (
            "photo", m.photo[-1].file_id, m.caption, m.caption_entities)
    elif m.video:
        kind, fid, text, ents = (
            "video", m.video.file_id, m.caption, m.caption_entities)
    elif m.animation:
        kind, fid, text, ents = (
            "animation", m.animation.file_id, m.caption, m.caption_entities)
    elif m.sticker:
        kind, fid, text, ents = "sticker", m.sticker.file_id, "", None
    elif m.text:
        kind, fid, text, ents = "text", None, m.text, m.entities
    else:
        return None
    return {
        "kind": kind, "file_id": fid, "text": text or "",
        "entities": [e.model_dump(exclude_none=True) for e in (ents or [])],
        "buttons": [],
    }


def ad_to_post(row):
    return {
        "kind": row["kind"], "file_id": row["file_id"],
        "text": row["text"] or "",
        "entities": json.loads(row["entities"] or "[]"),
        "buttons": json.loads(row["buttons"] or "[]"),
    }


async def send_post(bot, chat_id, post, markup=None):
    ents = [MessageEntity(**e) for e in post.get("entities") or []] or None
    kb = markup or buttons_markup(post.get("buttons"))
    kind = post["kind"]
    text = post.get("text") or None
    if kind == "photo":
        return await bot.send_photo(
            chat_id, post["file_id"], caption=text,
            caption_entities=ents, reply_markup=kb)
    if kind == "video":
        return await bot.send_video(
            chat_id, post["file_id"], caption=text,
            caption_entities=ents, reply_markup=kb)
    if kind == "animation":
        return await bot.send_animation(
            chat_id, post["file_id"], caption=text,
            caption_entities=ents, reply_markup=kb)
    if kind == "sticker":
        return await bot.send_sticker(
            chat_id, post["file_id"], reply_markup=kb)
    return await bot.send_message(
        chat_id, post["text"], entities=ents, reply_markup=kb,
        link_preview_options=NO_PREVIEW)


async def axionna_view(chat_id, greeting=False):
    """Показ рекламы Axionna (сервер Axionna сам шлёт пост в этот чат).
    Работает, если у сервиса axionna в «Спонсоры» есть ключ и он включён."""
    s = await get_sponsor("axionna")
    if not s or not s["enabled"] or not s["api_key"]:
        return
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.post(
                "https://axionna.org/api/views",
                headers={"Authorization": f"Bearer {s['api_key']}"},
                json={"chat_id": chat_id, "greeting": bool(greeting),
                      "impression_id": uuid.uuid4().hex},
            ) as r:
                data = await r.json(content_type=None)
        if not data.get("delivered"):
            logging.info("axionna view not delivered: %s", data)
    except Exception as e:
        logging.warning("axionna view error: %s", e)


async def show_ad(bot, chat_id):
    """Показывает следующий твой показ по кругу, затем показ Axionna."""
    ad = await next_ad()
    if ad:
        try:
            await send_post(bot, chat_id, ad_to_post(ad))
            await count_ad_show(ad["id"])
        except Exception as e:
            logging.warning("ad %s send error: %s", ad["id"], e)
    await axionna_view(chat_id)


async def safe_edit(call, text, kb=None):
    """Редактирует сообщение; если нельзя, отправляет новое."""
    try:
        await call.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=kb)
