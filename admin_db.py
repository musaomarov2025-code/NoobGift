import asyncio
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

from ads import safe_edit
from config import ADMIN_IDS, BACKUP_HOURS, DB_PATH, MSK
from database import import_old_users, init_db
from keyboards import back_kb, db_kb

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class DbForm(StatesGroup):
    file = State()
    json_file = State()


def _backup_sync(dst):
    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(dst)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()


async def make_backup():
    name = f"stars_{datetime.now(MSK):%Y%m%d_%H%M}.db"
    path = os.path.join(tempfile.gettempdir(), name)
    await asyncio.to_thread(_backup_sync, path)
    return path


def _valid(path):
    try:
        con = sqlite3.connect(path)
        try:
            ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        return ok and "users" in tables
    except Exception:
        return False


async def backup_loop(bot: Bot):
    """Присылает админам копию базы каждые BACKUP_HOURS часов."""
    while True:
        await asyncio.sleep(BACKUP_HOURS * 3600)
        try:
            path = await make_backup()
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_document(
                        admin_id, FSInputFile(path),
                        caption="💾 Автокопия базы")
                except Exception:
                    pass
            os.remove(path)
        except Exception:
            logging.exception("backup loop error")


@router.callback_query(F.data == "adm:db")
async def db_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        call,
        "💾 База данных\n\nСкачать: бот пришлёт файл базы.\n"
        "Загрузить: пришли файл .db, и он заменит текущую базу "
        "(старая сохранится как резервная копия).\n"
        "Размер файла до 20 МБ.\n"
        "Импорт из старого бота: пришли его .json, перенесу только "
        "пользователей для рассылки.\n\n"
        f"Автокопия приходит каждые {BACKUP_HOURS} ч.",
        db_kb())
    await call.answer()


@router.callback_query(F.data == "db:dl")
async def db_download(call: CallbackQuery):
    await call.answer("Готовлю файл…")
    path = await make_backup()
    try:
        await call.message.answer_document(
            FSInputFile(path), caption="💾 Копия базы")
    finally:
        os.remove(path)


@router.callback_query(F.data == "db:ul")
async def db_upload(call: CallbackQuery, state: FSMContext):
    await state.set_state(DbForm.file)
    await safe_edit(
        call,
        "Пришли файл базы (.db) документом.\n"
        "⚠️ Текущая база будет заменена.",
        back_kb("adm:db"))
    await call.answer()


@router.message(DbForm.file, F.document)
async def db_receive(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await message.answer("Файл больше 20 МБ, Telegram не даст его "
                             "скачать боту.")
        return
    tmp = os.path.join(os.path.dirname(DB_PATH), "upload_tmp.db")
    await bot.download(doc, destination=tmp)
    if not _valid(tmp):
        os.remove(tmp)
        await message.answer("Это не похоже на базу бота (нет таблицы "
                             "users). Пришли другой файл.")
        return
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, DB_PATH + ".bak")
    os.replace(tmp, DB_PATH)
    await init_db()  # добавит недостающие колонки и таблицы
    await state.clear()
    await message.answer("✅ База загружена и заменена.")


@router.message(DbForm.file)
async def db_wrong(message: Message):
    await message.answer("Пришли файл .db документом.")


@router.callback_query(F.data == "db:imp")
async def db_import(call: CallbackQuery, state: FSMContext):
    await state.set_state(DbForm.json_file)
    await safe_edit(
        call,
        "Пришли файл .json из старого бота документом.\n"
        "Перенесу только пользователей (ID и юзернейм) для рассылки, "
        "без балансов. Бонус за запуск они не получат.",
        back_kb("adm:db"))
    await call.answer()


@router.message(DbForm.json_file, F.document)
async def db_import_file(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await message.answer("Файл больше 20 МБ, Telegram не даст его "
                             "скачать боту.")
        return
    tmp = os.path.join(tempfile.gettempdir(), "old_users.json")
    await bot.download(doc, destination=tmp)
    try:
        with open(tmp, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        await message.answer("Не получилось прочитать файл: это не JSON. "
                             "Пришли другой файл.")
        return
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    items = data.get("users") if isinstance(data, dict) else data
    if not isinstance(items, list):
        await message.answer("В файле нет списка users. Пришли другой файл.")
        return
    added, skipped, bad = await import_old_users(items)
    await state.clear()
    await message.answer(
        "✅ Импорт завершён\n"
        f"Добавлено: {added}\n"
        f"Уже были в базе: {skipped}\n"
        f"Пропущено (нет ID): {bad}")


@router.message(DbForm.json_file)
async def db_import_wrong(message: Message):
    await message.answer("Пришли файл .json документом.")
