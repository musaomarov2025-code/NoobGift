from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from ads import safe_edit
from config import ADMIN_IDS, fmt, fmt_ts
from database import (
    get_stats, top_referrers, get_user, get_user_by_username,
    get_user_card, set_banned, add_balance, get_withdrawal,
    list_withdrawals, set_withdrawal_status, get_setting,
)
from keyboards import (
    back_kb, reqs_kb, req_kb, stats_kb, user_tools_kb,
)

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class UserForm(StatesGroup):
    find = State()
    amount = State()


def nm(r):
    return f"@{r['username']}" if r["username"] else (
        r["first_name"] or str(r["user_id"]))


def mask(s):
    s = s.lstrip("@")
    return (s[:2] + "***" + s[-2:]) if len(s) > 4 else (s[:1] + "***")


def card_body(c):
    u = c["user"]
    return (
        f"👤 {nm(u)} (ID {u['user_id']})\n"
        f"💰 Баланс: {u['balance']:.2f} ⭐\n"
        f"📋 Заданий выполнено: {u['tasks_done']}\n"
        f"👥 Приглашено: {c['invited']}\n"
        f"✅ Заданий у приглашённых: {c['ref_tasks']}\n"
        f"🔗 Пришёл по ссылке: "
        f"{u['referrer_id'] if u['referrer_id'] else 'нет'}\n"
        f"📅 Регистрация: {fmt_ts(u['created_at'])}\n"
        f"🛡 Проверка: {'пройдена' if u['verified'] else 'не пройдена'}\n"
        f"⚠️ Совпадения: по IP {c['dup_ip']}, по устройству {c['dup_fp']}\n"
        f"🚫 Бан: {'да' if u['banned'] else 'нет'}"
    )


async def card_text(uid):
    c = await get_user_card(uid)
    return card_body(c) if c else None


async def req_text(wid):
    w = await get_withdrawal(wid)
    if not w:
        return None, None
    c = await get_user_card(w["user_id"])
    status = {"new": "⏳ ожидает", "paid": "✅ выплачена",
              "rejected": "❌ отклонена"}.get(w["status"], w["status"])
    text = (
        f"💸 Заявка #{wid}\n"
        f"Сумма: {fmt(w['amount'])} ⭐\n"
        f"Статус: {status}\n"
        f"Создана: {fmt_ts(w['created_at'])}\n\n"
        + (card_body(c) if c else f"ID {w['user_id']}")
    )
    return text, w


# ---------- заявки ----------

@router.callback_query(F.data == "adm:reqs")
async def reqs(call: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = await list_withdrawals("new", 20)
    text = (f"💸 Заявок в ожидании: {len(rows)}" if rows
            else "💸 Новых заявок нет.")
    await safe_edit(call, text, reqs_kb(rows))
    await call.answer()


@router.callback_query(F.data == "rq:hist")
async def reqs_hist(call: CallbackQuery):
    rows = await list_withdrawals("done", 20)
    await safe_edit(call, "📜 Последние обработанные заявки",
                    reqs_kb(rows, history=True))
    await call.answer()


@router.callback_query(F.data.startswith("rq:open:"))
async def rq_open(call: CallbackQuery):
    wid = int(call.data.split(":")[2])
    text, w = await req_text(wid)
    if not w:
        await call.answer("Заявка не найдена", show_alert=True)
        return
    await safe_edit(call, text, req_kb(wid, w["user_id"], w["status"]))
    await call.answer()


async def _post_channel(bot: Bot, call: CallbackQuery, w):
    ch = await get_setting("payout_channel")
    if not ch:
        return
    u = await get_user(w["user_id"])
    name = mask(nm(u)) if u else "***"
    try:
        await bot.send_message(
            ch,
            f"✅ Выплата #{w['id']}\n\n"
            f"👤 {name}\n💎 {fmt(w['amount'])} ⭐")
    except Exception as e:
        await call.message.answer(
            f"Не получилось отправить в канал выплат: {e}")


async def _process(call: CallbackQuery, bot: Bot, status):
    wid = int(call.data.split(":")[2])
    w = await set_withdrawal_status(wid, status)
    if not w:
        await call.answer("Заявка уже обработана", show_alert=True)
        return
    amount = fmt(w["amount"])
    if status == "paid":
        note = f"✅ Заявка #{wid} на {amount} ⭐ выплачена!"
    else:
        note = f"❌ Заявка #{wid} на {amount} ⭐ отклонена!"
    try:
        await bot.send_message(w["user_id"], note)
    except Exception:
        pass
    if status == "paid":
        await _post_channel(bot, call, w)
    text, w2 = await req_text(wid)
    await safe_edit(call, text, req_kb(wid, w2["user_id"], w2["status"]))
    await call.answer("Готово")


@router.callback_query(F.data.startswith("rq:pay:"))
async def rq_pay(call: CallbackQuery, bot: Bot):
    await _process(call, bot, "paid")


@router.callback_query(F.data.startswith("rq:rej:"))
async def rq_reject(call: CallbackQuery, bot: Bot):
    await _process(call, bot, "rejected")


# ---------- статистика ----------

@router.callback_query(F.data == "adm:stats")
async def stats(call: CallbackQuery, state: FSMContext):
    await state.clear()
    s = await get_stats()
    by = "\n".join(f"   {n}: {c}" for n, c in s["by_sponsor"]) or "   —"
    text = (
        "📊 Статистика\n\n"
        f"👥 Пользователи: {s['users']} "
        f"(прошли проверку: {s['verified']})\n"
        f"➕ Новых: сегодня {s['new_today']}, за 7 дней {s['new_week']}\n\n"
        f"📋 Заданий выполнено: всего {s['tasks_total']}, "
        f"сегодня {s['tasks_today']}\n"
        f"🤝 По спонсорам:\n{by}\n\n"
        f"💰 Общий баланс пользователей: {s['balance']:.2f} ⭐\n"
        f"💸 Выплачено: {fmt(s['paid_sum'])} ⭐ ({s['paid_count']} зак.)\n"
        f"⏳ В ожидании: {s['pending_count']} зак. "
        f"на {fmt(s['pending_sum'])} ⭐"
    )
    await safe_edit(call, text, stats_kb())
    await call.answer()


@router.callback_query(F.data == "adm:top")
async def top(call: CallbackQuery):
    rows = await top_referrers(10)
    lines = ["🏆 Топ рефералов\n"]
    for i, r in enumerate(rows, 1):
        name = f"@{r['username']}" if r["username"] else (
            r["first_name"] or str(r["uid"]))
        lines.append(f"{i}. {name} (ID {r['uid']}): {r['n']}")
    if not rows:
        lines.append("Пока никого.")
    await safe_edit(call, "\n".join(lines), back_kb("adm:stats"))
    await call.answer()


# ---------- пользователь ----------

async def show_card(target, uid, edit_call=None):
    text = await card_text(uid)
    u = await get_user(uid)
    kb = user_tools_kb(uid, bool(u["banned"]))
    if edit_call:
        await safe_edit(edit_call, text, kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "adm:find")
async def find_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserForm.find)
    await safe_edit(call, "Отправь ID пользователя или @username:",
                    back_kb("adm:stats"))
    await call.answer()


@router.message(UserForm.find)
async def find_user(message: Message, state: FSMContext):
    t = (message.text or "").strip().lstrip("@")
    row = await get_user(int(t)) if t.isdigit() else (
        await get_user_by_username(t))
    if not row:
        await message.answer("Не нашёл. Отправь ID или @username ещё раз.")
        return
    await state.clear()
    await show_card(message, row["user_id"])


@router.callback_query(F.data.startswith("usr:open:"))
async def usr_open(call: CallbackQuery):
    uid = int(call.data.split(":")[2])
    if not await get_user(uid):
        await call.answer("Пользователь не найден", show_alert=True)
        return
    await show_card(call.message, uid, edit_call=call)
    await call.answer()


@router.callback_query(F.data.startswith("usr:ban:"))
async def usr_ban(call: CallbackQuery):
    uid = int(call.data.split(":")[2])
    u = await get_user(uid)
    if not u:
        await call.answer("Пользователь не найден", show_alert=True)
        return
    await set_banned(uid, not u["banned"])
    await show_card(call.message, uid, edit_call=call)
    await call.answer("Готово")


@router.callback_query(F.data.startswith("usr:add:"))
@router.callback_query(F.data.startswith("usr:sub:"))
async def usr_balance(call: CallbackQuery, state: FSMContext):
    _, mode, uid = call.data.split(":")
    await state.set_state(UserForm.amount)
    await state.update_data(uid=int(uid), sign=1 if mode == "add" else -1)
    word = "начислить" if mode == "add" else "списать"
    await call.message.answer(f"Сколько ⭐ {word}? Отправь число.",
                              reply_markup=back_kb("adm:stats"))
    await call.answer()


@router.message(UserForm.amount)
async def usr_balance_save(message: Message, state: FSMContext):
    try:
        amount = float((message.text or "").replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно положительное число, например 5")
        return
    data = await state.get_data()
    await add_balance(data["uid"], data["sign"] * amount)
    await state.clear()
    await show_card(message, data["uid"])
