import asyncio
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import (
    BOT_TOKEN, ADMIN_ID, GIFTS, GIFTS_EMOJI, REFERRAL_DAYS, DB,
    PIARFLOW_URL, TRAFFY_URL, TGRASS_URL,
)
from database import (
    init_db, get_setting, set_setting,
    get_user, add_user, update_username, add_balance, get_balance,
    get_place, can_take_bonus, set_bonus_taken,
    get_all_user_ids,
    is_welcome_bonus_paid, mark_welcome_bonus_paid,
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, get_user_referrals,
    confirm_referral, expire_old_referrals,
    get_refs_to_remind, mark_reminded,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_withdrawal_history,
    get_stats, get_top_balance, get_top_refs,
    create_promo, get_promo, list_promos, delete_promo,
    activate_promo, get_promo_uses_list,
    get_next_custom_task, mark_custom_task_done,
    add_ad_source, get_ad_source, list_ad_sources, delete_ad_source,
    mark_ad_user, mark_ad_user_op, mark_ad_user_blocked,
    increment_ad_refs, add_ad_stars, get_ad_stats_period,
    increment_ad_click,
    set_waiting_withdraw, get_waiting_withdraw, delete_waiting_withdraw,
    mark_task_completed, was_task_completed,
    get_task_stats,
    get_pending_withdrawals_all,
    count_pending_withdrawals, accept_all_pending, reject_all_pending,
    pf_save_offers, pf_get_next_offer, pf_mark_offer,
    pf_restore_skipped_if_old,
    export_users_to_json, import_users_from_json,
)
from services.tgrass import (
    tgrass_enabled, get_offers as tgrass_get_offers,
    get_tasks as tgrass_get_tasks, check_offer as tgrass_check_offer,
)
from services.traffy import (
    traffy_enabled, get_tasks as traffy_get_tasks,
    check_tasks as traffy_check_tasks,
)
from services.piarflow import (
    piarflow_enabled, get_sponsors as piarflow_get_sponsors,
    check as piarflow_check,
)
from keyboards import (
    main_menu, earn_kb, profile_kb, gifts_kb,
    daily_bonus_kb, daily_back_kb, promo_cancel_kb,
    admin_kb, admin_wd_kb, priv_kb, settings_kb,
    promos_kb, promo_list_kb, promo_view_kb,
    user_view_kb, back_admin_kb,
    tasks_kb, stats_kb,
    op_screen_kb, friends_check_kb,
    broadcast_menu_kb, broadcast_confirm_kb, broadcast_preview_kb,
    ad_menu_kb,
    wd_page_kb, wd_empty_kb,
    op_services_kb, op_service_detail_kb, api_keys_kb, user_manage_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_ID = int(BOT_TOKEN.split(":")[0]) if BOT_TOKEN else 0


# ================== ХЕЛПЕР ==================
def _smart_text(message):
    try:
        return message.html_text or message.text or ""
    except AttributeError:
        return message.text or ""


def _ensure_user_offers_table():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS user_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        service TEXT,
        offer_id TEXT,
        title TEXT,
        link TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_offers_user ON user_offers(user_id, status)")
    conn.commit()
    conn.close()


def _get_next_user_offer(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, service, offer_id, title, link FROM user_offers "
        "WHERE user_id = ? AND status = 'pending' ORDER BY id LIMIT 1",
        (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def _save_user_offer(user_id, service, offer_id, title, link):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_offers (user_id, service, offer_id, title, link, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, service, str(offer_id), title or "", link, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def _mark_user_offer(offer_row_id, status):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE user_offers SET status = ? WHERE id = ?", (status, offer_row_id))
    conn.commit()
    conn.close()


def _clear_user_offers(user_id, only_pending=True):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    if only_pending:
        cur.execute("DELETE FROM user_offers WHERE user_id = ? AND status = 'pending'", (user_id,))
    else:
        cur.execute("DELETE FROM user_offers WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def _has_pending_user_offers(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_offers WHERE user_id = ? AND status = 'pending' LIMIT 1", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


# ================== FSM ==================
class PromoCreate(StatesGroup):
    waiting_amount_min = State()
    waiting_amount_max = State()
    waiting_uses = State()

class PromoDelete(StatesGroup):
    waiting_code = State()

class SetValue(StatesGroup):
    waiting_value = State()

class UserPromo(StatesGroup):
    waiting_code = State()

class PrivEdit(StatesGroup):
    waiting_text = State()
    waiting_buttons = State()

class UserManage(StatesGroup):
    waiting_id = State()
    waiting_amount = State()

class TasksEdit(StatesGroup):
    waiting_reward = State()

class AdAdd(StatesGroup):
    waiting_code = State()
    waiting_owner = State()
    waiting_price = State()

class AdDel(StatesGroup):
    waiting_code = State()

class BroadcastFlow(StatesGroup):
    waiting_text = State()
    waiting_media = State()
    waiting_buttons = State()
    waiting_count = State()

class APIKeyEdit(StatesGroup):
    waiting_key = State()

class OSDetailEdit(StatesGroup):
    waiting_value = State()


# ============ TGRASS / TRAFFY ОБЁРТКИ ============
def _user_kwargs(user):
    return {
        "username": getattr(user, "username", None),
        "first_name": getattr(user, "first_name", None),
        "lang": getattr(user, "language_code", None) or "ru",
    }


async def _traffy_items(user_id, limit, user):
    if not (traffy_enabled() and get_setting("traffy_api_key")):
        return []
    data = await traffy_get_tasks(user_id, limit=limit, **_user_kwargs(user))
    items = []
    if data.get("ok") and data.get("tasks"):
        for t in data["tasks"]:
            aid = t.get("assignment_id")
            link = t.get("target_link")
            if not aid or not link:
                continue
            items.append((
                f"traffy:{aid}",
                t.get("button_text") or "Подписаться",
                link,
                False,
            ))
    return items


async def _tgrass_items(user_id, limit, user, for_tasks=False):
    if not (tgrass_enabled() and get_setting("tgrass_api_key")):
        return []
    kwargs = _user_kwargs(user)
    premium = bool(getattr(user, "is_premium", False))
    fn = tgrass_get_tasks if for_tasks else tgrass_get_offers
    data = await fn(
        user_id,
        username=kwargs["username"],
        lang=kwargs["lang"],
        is_premium=premium,
        limit=limit,
    )
    status = data.get("status")
    if status not in ("ok", "not_ok"):
        return []
    items = []
    for o in data.get("offers") or []:
        oid = o.get("offer_id")
        link = o.get("link")
        if not oid or not link:
            continue
        if o.get("subscribed"):
            continue
        items.append((
            f"tgrass:{oid}",
            o.get("name") or "Подписаться",
            link,
            False,
        ))
    return items


# ============ ОП: СБОР + ПРОВЕРКА ============
async def collect_op_items(user_id, user=None, limit=6):
    """Traffy → если пусто → Tgrass. Если оба пусты — пустой список."""
    items = []
    if user is None:
        # fallback: без user данных, используем минимальные
        class _U:
            username = None
            first_name = None
            language_code = "ru"
            is_premium = False
        user = _U()

    try:
        items = await _traffy_items(user_id, limit, user)
    except Exception as e:
        print("traffy items error:", e)
        items = []

    if not items:
        try:
            items = await _tgrass_items(user_id, limit, user)
        except Exception as e:
            print("tgrass items error:", e)
            items = []

    return items


async def check_op_items(user_id, items):
    """Проверяет все items. True — всё выполнено. False — есть непройденные."""
    if not items:
        return True

    traffy_ids = []
    tgrass_ids = []
    for key, _, _, _ in items:
        if key.startswith("traffy:"):
            traffy_ids.append(key.split(":", 1)[1])
        elif key.startswith("tgrass:"):
            tgrass_ids.append(key.split(":", 1)[1])

    all_ok = True

    if traffy_ids:
        try:
            data = await traffy_check_tasks(user_id, traffy_ids)
            if not data.get("ok"):
                all_ok = False
            else:
                for r in data.get("results", []):
                    if r.get("status") != "completed":
                        all_ok = False
        except Exception as e:
            print("traffy check error:", e)
            all_ok = False

    if tgrass_ids:
        for oid in tgrass_ids:
            try:
                data = await tgrass_check_offer(user_id, int(oid))
                if data.get("status") != "subscribed":
                    all_ok = False
            except Exception as e:
                print("tgrass check error:", e)
                all_ok = False

    return all_ok


async def send_op_screen(chat_id, user_id, user=None, header_text=None,
                         confirm_callback="op_check"):
    items = await collect_op_items(user_id, user=user)
    if not items:
        return True
    text = header_text if header_text else get_setting("tgrass_text")
    kb = op_screen_kb(items, confirm_callback=confirm_callback)
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    return False


async def _guard_ops(message_or_call):
    if isinstance(message_or_call, Message):
        user = message_or_call.from_user
        user_id = user.id
        chat_id = message_or_call.chat.id
    else:
        user = message_or_call.from_user
        user_id = user.id
        chat_id = user.id

    items = await collect_op_items(user_id, user=user)
    if not items:
        return True

    await bot.send_message(
        chat_id,
        get_setting("tgrass_text"),
        reply_markup=op_screen_kb(items),
        parse_mode="HTML")
    return False


# ============ ПЕРЕХОД В МЕНЮ ============
async def _send_earn_screen(chat_id, user_id):
    me = await bot.get_me()
    ref_bonus = get_setting("ref_bonus")
    refs = get_confirmed_refs_count(user_id)
    ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    share_text = "Заходи в бота, тут раздают звёзды ⭐"
    share_url = (f"https://t.me/share/url?url={quote(ref_link, safe='')}"
                 f"&text={quote(share_text, safe='')}")

    text = (
        f'Приглашай пользователей в бота и получай по {ref_bonus} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji> '
        f'как только они подпишутся на каналы!\n\n'
        f'<tg-emoji emoji-id="5260730055880876557">⛓</tg-emoji><b>Ваша ссылка:</b>\n'
        f'{ref_link}\n\n'
        f'<blockquote>'
        f'<tg-emoji emoji-id="5361948905900635660">❓</tg-emoji> <b>Как использовать реферальную ссылку?</b>\n'
        f'• Отправь её друзьям в личные сообщения <tg-emoji emoji-id="5258513401784573443">👥</tg-emoji>\n'
        f'• Поделись ссылкой в своём Telegram-канале <tg-emoji emoji-id="5258236805890710909">⬅️</tg-emoji>\n'
        f'• Оставь её в комментариях или чатах <tg-emoji emoji-id="5258215850745275216">➡️</tg-emoji>\n'
        f'• Распространяй ссылку в соцсетях: TikTok, Instagram, WhatsApp и других '
        f'<tg-emoji emoji-id="5258057130228849960">✅</tg-emoji>'
        f'</blockquote>\n\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> Вы пригласили: <b>{refs}</b>'
    )
    await bot.send_message(chat_id, text, reply_markup=earn_kb(share_url), parse_mode="HTML")


async def _go_to_main(chat_id, user_id):
    await bot.send_message(chat_id, "👇", reply_markup=main_menu())
    await _send_earn_screen(chat_id, user_id)


# ============ ЭКРАН "N ДРУЗЕЙ" ============
def _friends_required():
    try:
        return int(get_setting("withdraw_friends_required") or 2)
    except Exception:
        return 2


async def _show_friends_screen(target, user_id, edit_message=False):
    w = get_waiting_withdraw(user_id)
    if not w:
        return
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    done = min(need, refs_now)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    text = (
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> '
        f'<b>Чтобы получить подарок — пригласи {need} друзей!</b>\n\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> '
        f'Прогресс: <b>{done}/{need}</b>\n\n'
        f'<tg-emoji emoji-id="5318757666800031348">✅</tg-emoji> '
        f'<b>Твоя ссылка:</b>\n{ref_link}\n\n'
        f'<blockquote><tg-emoji emoji-id="5452069934089641166">❓</tg-emoji> '
        f'Друг должен зайти по ссылке и забрать бонус</blockquote>'
    )
    kb = friends_check_kb()

    if edit_message and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    if isinstance(target, int):
        await bot.send_message(target, text, reply_markup=kb, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


async def _check_and_fulfill_waiting(user_id):
    w = get_waiting_withdraw(user_id)
    if not w:
        return False
    _, gift_key, _ = w
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    if refs_now < need:
        return False
    if gift_key not in GIFTS:
        delete_waiting_withdraw(user_id)
        return False
    name, price = GIFTS[gift_key]
    balance = get_balance(user_id)
    if balance < price:
        return False

    wid = create_withdrawal(user_id, price, gift_key)
    delete_waiting_withdraw(user_id)

    new_balance = get_balance(user_id)
    gift_emoji_id = GIFTS_EMOJI.get(gift_key, "")

    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> '
        f'<b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Твой баланс: <b>{new_balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass

    u = get_user(user_id)
    uname = f"@{u[1]}" if u and u[1] else "без username"
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{user_id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка админу:", e)
    return True


# ============ СТАРТ ============
def _parse_start_arg(arg):
    if not arg:
        return None, None
    if arg.startswith("ref_"):
        return "ref", arg[4:]
    if arg.startswith("ad_"):
        return "ad", arg[3:]
    if arg.startswith("promo_"):
        return "promo", arg[6:]
    return None, None


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    start_arg = args[1] if len(args) > 1 else ""
    kind, value = _parse_start_arg(start_arg)

    referrer = None
    ad_code = None
    promo_code = None

    if kind == "ref":
        try:
            referrer = int(value)
        except Exception:
            referrer = None
    elif kind == "ad":
        ad_code = value
    elif kind == "promo":
        promo_code = value.upper()

    u = message.from_user
    is_new = add_user(u.id, u.username, referrer)
    if not is_new:
        update_username(u.id, u.username)

    if not is_welcome_bonus_paid(u.id):
        try:
            bonus = int(get_setting("welcome_bonus") or 15)
        except Exception:
            bonus = 15
        if bonus > 0:
            add_balance(u.id, bonus)
            mark_welcome_bonus_paid(u.id)
            try:
                await message.answer(
                    f'<tg-emoji emoji-id="5895708410447401643">⭐️</tg-emoji> '
                    f'<b>Вы получили {bonus} Звёзд за запуск бота!</b>',
                    parse_mode="HTML")
            except Exception:
                pass

    if is_new and referrer and referrer != u.id:
        create_pending_referral(u.id, referrer)
        try:
            await bot.send_message(referrer,
                '<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
                '<b>По твоей ссылке зашёл новый друг!</b>\n\n'
                'Он должен зайти в прочее и забрать бонус — тогда ты получишь звёзды.',
                parse_mode="HTML")
        except Exception:
            pass

    if ad_code:
        src = get_ad_source(ad_code)
        if src:
            increment_ad_click(ad_code, is_new_user=is_new)
            is_premium = 1 if getattr(u, "is_premium", False) else 0
            mark_ad_user(u.id, ad_code,
                         registered=1 if is_new else 0,
                         is_premium=is_premium)

    if get_setting("priv_enabled") == "1":
        priv_text = get_setting("priv_text")
        kb = build_priv_buttons()
        if kb:
            await message.answer(priv_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(priv_text, parse_mode="HTML")

    await asyncio.sleep(2)

    # Промокод активируем, но ОП НЕ обходим.
    # Если что-то пойдёт не так (юзер не подписан) — код будет отложен до ручного ввода.
    if promo_code:
        promo = get_promo(promo_code)
        if promo:
            ok, msg_, amt = activate_promo(promo_code, u.id)
            if ok:
                add_ad_stars(u.id, amt)
                try:
                    await message.answer(f"✅ Промокод активирован! +{amt} ⭐")
                except Exception:
                    pass
            else:
                try:
                    await message.answer(msg_, parse_mode="HTML")
                except Exception:
                    pass

    # ОП
    passed = await send_op_screen(message.chat.id, u.id, user=u)
    if not passed:
        return

    await _go_to_main(message.chat.id, u.id)


@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = call.from_user

    items_before = await collect_op_items(user_id, user=user)
    all_ok = await check_op_items(user_id, items_before)

    if all_ok or not items_before:
        await call.answer()
        try:
            await call.message.delete()
        except Exception:
            pass
        mark_ad_user_op(user_id)
        await _go_to_main(user_id, user_id)
        return

    # Показываем оставшиеся
    items_after = await collect_op_items(user_id, user=user)
    if not items_after:
        await call.answer()
        try:
            await call.message.delete()
        except Exception:
            pass
        mark_ad_user_op(user_id)
        await _go_to_main(user_id, user_id)
        return

    await call.answer("Ты подписался не на всё", show_alert=True)
    text = get_setting("tgrass_text")
    kb = op_screen_kb(items_after, confirm_callback="op_check")
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


# ============ ПРИВАТКА ============
def build_priv_buttons():
    raw = get_setting("priv_buttons")
    if not raw:
        return None
    rows = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        row = []
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " not in pair:
                continue
            parts = pair.split(" - ", 1)
            text = parts[0].strip()
            url = parts[1].strip()
            if text and url:
                row.append(InlineKeyboardButton(text=text, url=url))
        if row:
            rows.append(row)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "Заработать звёзды")
async def earn(message: Message):
    if not await _guard_ops(message):
        return
    await _send_earn_screen(message.chat.id, message.from_user.id)


# ============ ПРОЧЕЕ ============
def _profile_text(uid: int, first_name: str) -> str:
    u = get_user(uid)
    balance = u[2] if u else 0
    name = first_name or "друг"
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    place = get_place(uid)
    return (
        f'<tg-emoji emoji-id="5260399854500191689">👤</tg-emoji> <b>ПРОЧЕЕ</b>\n\n'
        f'<tg-emoji emoji-id="5389099588906922686">🧑</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="6030656587830399914">🆔</tg-emoji> <code>{uid}</code>\n\n'
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji> Баланс: <b>{balance}.00</b>\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> Друзей: <b>{refs}</b>\n'
        f'<tg-emoji emoji-id="5386367538735104399">⌛</tg-emoji> Ожидают: <b>{pending}</b>\n'
        f'<tg-emoji emoji-id="5474419165781597383">🏆</tg-emoji> Место в топе: <b>#{place}</b>\n\n'
        f'<tg-emoji emoji-id="5231102735817918643">👇</tg-emoji> Забирай бонусы и промокоды'
    )


async def _render_profile(call: CallbackQuery):
    if not get_user(call.from_user.id):
        try:
            await call.message.delete()
        except Exception:
            pass
        return
    text = _profile_text(call.from_user.id, call.from_user.first_name)
    try:
        await call.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.message(F.text == "Прочее")
async def profile(message: Message):
    if not get_user(message.from_user.id):
        await message.answer("Напиши /start")
        return
    if not await _guard_ops(message):
        return
    text = _profile_text(message.from_user.id, message.from_user.first_name)
    await message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(call: CallbackQuery):
    balance = get_balance(call.from_user.id)
    if not can_take_bonus(call.from_user.id):
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
            f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Бонус уже получен сегодня!\n\n'
            f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {balance} '
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
            reply_markup=daily_back_kb(), parse_mode="HTML")
        return
    await call.message.edit_text(
        f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Собирай ежедневный бонус каждый день!\n\n'
        f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {balance} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
        reply_markup=daily_bonus_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_claim")
async def daily_claim(call: CallbackQuery):
    if not can_take_bonus(call.from_user.id):
        await call.answer("⏳ Уже забирал сегодня!", show_alert=True)
        return
    amount = int(get_setting("daily_bonus"))
    add_balance(call.from_user.id, amount)
    set_bonus_taken(call.from_user.id)
    balance = get_balance(call.from_user.id)

    referrer = confirm_referral(call.from_user.id)
    if referrer:
        ref_bonus = int(get_setting("ref_bonus"))
        add_balance(referrer, ref_bonus)
        add_ad_stars(referrer, ref_bonus)
        increment_ad_refs(call.from_user.id)
        try:
            await bot.send_message(referrer,
                f'<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
                f'<b>Друг подтвердил реферал!</b>\n\n'
                f'<tg-emoji emoji-id="5469744063815102906">💫</tg-emoji> '
                f'Тебе начислено <b>+{ref_bonus}</b> '
                f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>',
                parse_mode="HTML")
        except Exception:
            pass

    await call.answer()
    try:
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневный бонус получен!</b>\n\n'
            f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> +{amount}'
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>\n'
            f'<tg-emoji emoji-id="5920281855378068765">⭐️</tg-emoji> Баланс: {balance} '
            f'<tg-emoji emoji-id="5897501460509234625">⭐️</tg-emoji>',
            reply_markup=daily_back_kb(), parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "daily_back")
async def daily_back(call: CallbackQuery):
    await _render_profile(call)


@dp.callback_query(F.data == "daily_cancel")
async def daily_cancel(call: CallbackQuery):
    await _render_profile(call)


# ============ ПРОМОКОД (ручной ввод) ============
@dp.callback_query(F.data == "enter_promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext):
    text = (
        f'<tg-emoji emoji-id="5197468864102823838">🎟</tg-emoji> <b>Промокоды</b>\n\n'
        f'Введите промокод для активации:'
    )
    try:
        await call.message.edit_text(text, reply_markup=promo_cancel_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=promo_cancel_kb(), parse_mode="HTML")
    await state.set_state(UserPromo.waiting_code)


@dp.callback_query(F.data == "promo_cancel")
async def promo_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_profile(call)


@dp.message(UserPromo.waiting_code)
async def user_promo_check(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    await state.clear()
    promo = get_promo(code)
    if not promo:
        await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
            f'<b>Промокод не найден</b>\n\n'
            f'Проверьте правильность написания и попробуйте снова',
            parse_mode="HTML")
        return

    ok, msg_, amt = activate_promo(code, message.from_user.id)
    if ok:
        add_ad_stars(message.from_user.id, amt)
        balance = get_balance(message.from_user.id)
        await message.answer(
            f"✅ <b>Промокод активирован!</b>\n\n"
            f"💰 +{amt}.00 ⭐\n⭐️ Баланс: <b>{balance}.00</b>",
            parse_mode="HTML")
    else:
        await message.answer(msg_, parse_mode="HTML")


# ============ /stat_XXX ============
@dp.message(F.text.regexp(r"^/stat_[A-Za-z0-9_]+$"))
async def ad_stats_cmd(message: Message):
    user_id = message.from_user.id
    code = message.text[len("/stat_"):].strip().lower()

    src = get_ad_source(code)
    if not src:
        await message.answer("❌ Такой метки не существует.")
        return
    if src[1] != user_id and user_id != ADMIN_ID:
        await message.answer("❌ У тебя нет доступа к этой метке.")
        return

    owner_username = src[2] or ""
    price_per_click = src[5] if len(src) > 5 else 0

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ad_{code}"

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    yest_start = today_start - timedelta(days=1)

    total = get_ad_stats_period(code)
    today = get_ad_stats_period(code, today_start.isoformat(), today_end.isoformat())
    yest = get_ad_stats_period(code, yest_start.isoformat(), today_start.isoformat())

    def pct(a, b):
        if not b:
            return 0
        return round(a / b * 100)

    def block(title, s):
        clicks = s["clicks"]
        users = s["users"]
        registered = s["registered"]
        op = s["op"]
        return (
            f"<b>{title}</b>\n"
            f"Переходов: <b>{clicks}</b>\n"
            f"Пользователей: <b>{users}</b> ({pct(users, clicks)}%)\n"
            f"Зарегистрированных: <b>{registered}</b> ({pct(registered, clicks)}%)\n"
            f"Подписки: <b>{op}</b> ({pct(op, clicks)}%)\n"
        )

    users_total = total["users"]
    blocked = total["blocked"]
    alive = users_total - blocked
    premium = total["premium"]
    uniq = total["op"]
    non_uniq = users_total - uniq
    spent = price_per_click * total["clicks"]
    stars = total["stars"]

    text = (
        f"🍑 <b>Статистика</b>\n\n"
        f"{block('Всего', total)}\n"
        f"{block('За вчера', yest)}\n"
        f"{block('За сегодня', today)}\n"
        f"Живых: <b>{alive}</b> ({pct(alive, users_total)}%)\n"
        f"Мертвых: <b>{blocked}</b> ({pct(blocked, users_total)}%)\n\n"
        f"Уникальных: <b>{uniq}</b>\n"
        f"Не уникальных: <b>{non_uniq}</b> ({pct(non_uniq, users_total)}%)\n"
        f"Премиум: <b>{premium}</b> ({pct(premium, users_total)}%) 💎\n\n"
        f"💰 Цена перехода: <b>{price_per_click}</b> ₽\n"
        f"💸 Потрачено: <b>{spent}</b> ₽\n"
        f"⭐ Заработали звёзд: <b>{stars}</b>\n\n"
        f"👤 Рекламодатель: <b>@{owner_username}</b>\n"
        f"🔗 <b>Реф-ссылка:</b>\n<code>{ref_link}</code>"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await message.answer(text, parse_mode="HTML")


# ============ ЗАДАНИЯ: Traffy → Tgrass → PiarFlow ============
async def _show_tasks(message, user_id, chat_id):
    try:
        pf_restore_skipped_if_old(user_id, hours=1)
    except Exception as e:
        print("pf_restore error:", e)

    # 1) Если есть pending оффер в БД — показываем его
    row = _get_next_user_offer(user_id)
    if row:
        await _render_user_offer(message, user_id, row)
        return

    # 2) Пробуем Traffy
    user = message.from_user
    try:
        items = await _traffy_items(user_id, limit=10, user=user)
    except Exception as e:
        print("traffy items error:", e)
        items = []

    # 3) Если Traffy пусто — Tgrass
    if not items:
        try:
            items = await _tgrass_items(user_id, limit=10, user=user, for_tasks=True)
        except Exception as e:
            print("tgrass tasks error:", e)
            items = []

    # 4) Сохраняем в БД
    if items:
        for key, title, link, _ in items:
            service, offer_id = key.split(":", 1)
            _save_user_offer(user_id, service, offer_id, title, link)
        row = _get_next_user_offer(user_id)
        if row:
            await _render_user_offer(message, user_id, row)
            return

    # 5) Fallback — PiarFlow (как раньше)
    await _show_piarflow_tasks(message, user_id, chat_id)


async def _render_user_offer(message, user_id, row):
    row_id, service, offer_id, title, link = row
    reward = int(get_setting("task_reward") or 5)

    if service == "traffy":
        provider = "📊 Traffy"
    elif service == "tgrass":
        provider = "🌿 Tgrass"
    else:
        provider = "🎯"

    text = (
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> '
        f'<b>Задание от {provider}</b>\n\n'
        f'<tg-emoji emoji-id="5980930633298350051">✅</tg-emoji> '
        f'Подпишись и нажми «Подтвердить»\n\n'
        f'<b>{title or "Задание"}</b>\n\n'
        f'<b>Вознаграждение: +{reward} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji></b>'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти", url=link,
                              icon_custom_emoji_id="5368733682917980020"),
         InlineKeyboardButton(text="Пропустить", callback_data=f"task_skip:{row_id}",
                              icon_custom_emoji_id="5260450573768990626")],
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"task_check:{row_id}",
                              icon_custom_emoji_id="6026257381678124710")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "Задания")
async def tasks_menu(message: Message):
    if not await _guard_ops(message):
        return
    await _show_tasks(message, message.from_user.id, message.chat.id)


@dp.callback_query(F.data.startswith("task_skip:"))
async def task_skip_cb(call: CallbackQuery):
    try:
        row_id = int(call.data.split(":")[1])
    except Exception:
        await call.answer("Ошибка")
        return
    _mark_user_offer(row_id, "skipped")
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_tasks(call.message, call.from_user.id, call.from_user.id)


@dp.callback_query(F.data.startswith("task_check:"))
async def task_check_cb(call: CallbackQuery):
    user_id = call.from_user.id
    try:
        row_id = int(call.data.split(":")[1])
    except Exception:
        await call.answer("Ошибка")
        return

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT service, offer_id, link FROM user_offers WHERE id = ?", (row_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await call.answer("Задание не найдено, обнови", show_alert=True)
        return

    service, offer_id, link = row
    reward = int(get_setting("task_reward") or 5)

    done = False

    if service == "traffy":
        try:
            data = await traffy_check_tasks(user_id, [offer_id])
            if data.get("ok"):
                for r in data.get("results", []):
                    if r.get("assignment_id") == offer_id:
                        if r.get("status") == "completed":
                            done = True
                        break
        except Exception as e:
            print("traffy check err:", e)

    elif service == "tgrass":
        try:
            data = await tgrass_check_offer(user_id, int(offer_id))
            if data.get("status") == "subscribed":
                done = True
        except Exception as e:
            print("tgrass check err:", e)

    if not done:
        await call.answer("❌ Подпишись и попробуй ещё раз", show_alert=True)
        return

    add_balance(user_id, reward)
    add_ad_stars(user_id, reward)
    mark_task_completed(user_id, 0 if service == "traffy" else int(offer_id), reward)
    _mark_user_offer(row_id, "done")

    balance = get_balance(user_id)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Задание выполнено!</b>\n\n'
        f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> Награда: <b>+{reward}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> Баланс: <b>{balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Загружаю следующее задание...',
        parse_mode="HTML")

    await asyncio.sleep(1)
    await _show_tasks(call.message, user_id, user_id)


# ============ ЗАДАНИЯ (PIARFLOW) — как было ============
async def _show_piarflow_tasks(message, user_id, chat_id):
    if not piarflow_enabled():
        await message.answer(
            f'<tg-emoji emoji-id="5350460637182993292">🎉</tg-emoji> '
            f'<b>Ты молодец, выполнены все доступные задания!</b>\n\n'
            f'Новые задания скоро появятся…',
            parse_mode="HTML")
        return

    offer_id, link = pf_get_next_offer(user_id)

    if not offer_id:
        data = await piarflow_get_sponsors(user_id, chat_id, max_sponsors=10)
        if data.get("status") != "ok":
            await message.answer(
                f'<tg-emoji emoji-id="5350460637182993292">🎉</tg-emoji> '
                f'<b>Новых заданий пока нет</b>\n\nПопробуй позже.',
                parse_mode="HTML")
            return

        sponsors = data.get("sponsors", []) or []
        links = [s["link"] for s in sponsors if s.get("link")]
        if not links:
            await message.answer(
                f'<tg-emoji emoji-id="5350460637182993292">🎉</tg-emoji> '
                f'<b>Ты молодец, выполнены все доступные задания!</b>\n\n'
                f'<tg-emoji emoji-id="5920433463428650761">🔄</tg-emoji> '
                f'Новые задания скоро появятся…',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Обновить задания",
                                          callback_data="piarflow_refresh",
                                          icon_custom_emoji_id="5386367538735104399")]
                ]),
                parse_mode="HTML")
            return

        pf_save_offers(user_id, links)
        offer_id, link = pf_get_next_offer(user_id)

        if not offer_id:
            await message.answer("Ошибка: не удалось сохранить офферы.")
            return

    reward = int(get_setting("task_reward") or 5)

    text = (
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> '
        f'<b>Собирай Звёзды за простые задания!</b> '
        f'<tg-emoji emoji-id="5470177992950946662">👇</tg-emoji>\n\n'
        f'<tg-emoji emoji-id="5980930633298350051">✅</tg-emoji> '
        f'Подпишись на канал и нажми «Подтвердить»\n\n'
        f'<tg-emoji emoji-id="5765005318610228026">❌</tg-emoji> '
        f'За отписку или блокировку ресурса, вы получите бан\n\n'
        f'<b>Вознаграждение: +{reward} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji></b>'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти", url=link,
                              icon_custom_emoji_id="5368733682917980020"),
         InlineKeyboardButton(text="Пропустить", callback_data="piarflow_skip",
                              icon_custom_emoji_id="5260450573768990626")],
        [InlineKeyboardButton(text="Подтвердить", callback_data="piarflow_check",
                              icon_custom_emoji_id="6026257381678124710")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "piarflow_refresh")
async def piarflow_refresh(call: CallbackQuery):
    if not await _guard_ops(call):
        return
    try:
        await call.message.delete()
    except Exception:
        pass
    _clear_user_offers(call.from_user.id)
    await _show_tasks(call.message, call.from_user.id, call.from_user.id)


@dp.callback_query(F.data == "piarflow_skip")
async def piarflow_skip(call: CallbackQuery):
    user_id = call.from_user.id
    if not await _guard_ops(call):
        return

    offer_id, link = pf_get_next_offer(user_id)
    if offer_id:
        pf_mark_offer(offer_id, "skipped")

    try:
        await call.message.delete()
    except Exception:
        pass

    await _show_tasks(call.message, user_id, user_id)


@dp.callback_query(F.data == "piarflow_check")
async def piarflow_check_cb(call: CallbackQuery):
    user_id = call.from_user.id

    offer_id, link = pf_get_next_offer(user_id)
    if not offer_id:
        await call.answer("Задание не найдено, обнови", show_alert=True)
        return

    data = await piarflow_check(user_id, [link])
    sponsors = data.get("sponsors", []) or []
    ok = bool(sponsors) and all(
        s.get("status") in ("subscribed", "not_counted") for s in sponsors
    )

    if not ok:
        await call.answer("❌ Подпишись и попробуй ещё раз", show_alert=True)
        return

    reward = int(get_setting("task_reward") or 5)
    add_balance(user_id, reward)
    add_ad_stars(user_id, reward)
    mark_task_completed(user_id, offer_id, reward)

    pf_mark_offer(offer_id, "subscribed")

    balance = get_balance(user_id)
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Задание выполнено!</b>\n\n'
        f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> Награда: <b>+{reward}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> Баланс: <b>{balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Загружаю следующее задание...',
        parse_mode="HTML")

    await asyncio.sleep(1)
    await _show_tasks(call.message, user_id, user_id)


# ============ ВЫВОД ============
async def _show_gifts(chat_id, user_id):
    kb = gifts_kb()
    caption = '<tg-emoji emoji-id="5427236501903655352">❣️</tg-emoji> <b>Выбери подарок</b>'
    await bot.send_message(chat_id, caption, reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "Вывести звёзды")
async def withdraw(message: Message, state: FSMContext):
    if not await _guard_ops(message):
        return
    await state.clear()
    user_id = message.from_user.id
    chat_id = message.chat.id

    w = get_waiting_withdraw(user_id)
    if w:
        await _show_friends_screen(message, user_id)
        return

    await _show_gifts(chat_id, user_id)


@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift(call: CallbackQuery, state: FSMContext):
    if not await _guard_ops(call):
        return
    key = call.data.split(":")[1]
    if key not in GIFTS:
        await call.answer("Подарок не найден")
        return
    name, price = GIFTS[key]
    balance = get_balance(call.from_user.id)
    if balance < price:
        need_sum = price - balance
        await call.answer(f"❌ Не хватает {need_sum} ⭐\nНужно: {price} ⭐\nУ тебя: {balance} ⭐",
                          show_alert=True)
        return

    user_id = call.from_user.id
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)

    if refs_now >= need:
        try:
            await call.message.delete()
        except Exception:
            pass
        await create_order(call, key)
        return

    set_waiting_withdraw(user_id, key)
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_friends_screen(user_id, user_id)


@dp.callback_query(F.data == "wd_friends_check")
async def wd_friends_check_cb(call: CallbackQuery):
    user_id = call.from_user.id
    ok = await _check_and_fulfill_waiting(user_id)
    await call.answer("Обновлено", show_alert=True)
    if ok:
        try:
            await call.message.delete()
        except Exception:
            pass
        return
    w = get_waiting_withdraw(user_id)
    if not w:
        return
    await _show_friends_screen(call, user_id, edit_message=True)


async def create_order(call: CallbackQuery, key):
    name, price = GIFTS[key]
    gift_emoji_id = GIFTS_EMOJI.get(key, "")
    balance = get_balance(call.from_user.id)
    if balance < price:
        await call.answer(f"❌ Нужно {price} ⭐", show_alert=True)
        return
    wid = create_withdrawal(call.from_user.id, price, key)
    new_balance = get_balance(call.from_user.id)
    uname = f"@{call.from_user.username}" if call.from_user.username else "без username"

    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Твой баланс: <b>{new_balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )
    try:
        await bot.send_message(call.from_user.id, text, parse_mode="HTML")
    except Exception as e:
        print("Ошибка юзеру:", e)
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка админу:", e)


# ================== АДМИНКА ==================
@dp.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    s = get_stats()
    t_all = get_task_stats()
    await message.answer(
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        f"👥 Пользователей: <b>{s['total']}</b>\n"
        f"📋 Заявок в ожидании: <b>{s['pending']}</b>\n"
        f"✅ Заданий выполнено: <b>{t_all['count']}</b>",
        reply_markup=admin_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    s = get_stats()
    t_all = get_task_stats()
    try:
        await call.message.edit_text(
            f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            f"👥 Пользователей: <b>{s['total']}</b>\n"
            f"📋 Заявок в ожидании: <b>{s['pending']}</b>\n"
            f"✅ Заданий выполнено: <b>{t_all['count']}</b>",
            reply_markup=admin_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer("🛠 Админ-панель", reply_markup=admin_kb())


# ---------- ОП-СЕРВИСЫ ----------
def _os_menu_text():
    tg = tgrass_enabled()
    tr = traffy_enabled()
    return (
        f"🎯 <b>ОП-сервисы</b>\n\n"
        f"🌿 Tgrass: {'🟢 включён' if tg else '🔴 выключен'} "
        f"(вход: {get_setting('tgrass_entry_count')}, вывод: {get_setting('tgrass_withdraw_count')})\n"
        f"📊 Traffy: {'🟢 включён' if tr else '🔴 выключен'} "
        f"(вход: {get_setting('traffy_entry_count')}, вывод: {get_setting('traffy_withdraw_count')})\n\n"
        f"Порядок проверки: Traffy → Tgrass."
    )


@dp.callback_query(F.data == "op_services")
async def op_services_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        await call.message.edit_text(_os_menu_text(),
                                      reply_markup=op_services_kb(tgrass_enabled(), traffy_enabled()),
                                      parse_mode="HTML")
    except Exception:
        await call.message.answer(_os_menu_text(),
                                   reply_markup=op_services_kb(tgrass_enabled(), traffy_enabled()),
                                   parse_mode="HTML")


@dp.callback_query(F.data.startswith("os_tgrass"))
async def os_tgrass_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    if call.data == "os_tgrass":
        await call.message.edit_text(
            f"🌿 <b>Tgrass</b>\n\n"
            f"Вход: <b>{get_setting('tgrass_entry_count')}</b>\n"
            f"Вывод: <b>{get_setting('tgrass_withdraw_count')}</b>",
            reply_markup=op_service_detail_kb("tgrass", tgrass_enabled()),
            parse_mode="HTML")
        return
    if call.data == "os_tgrass_toggle":
        set_setting("tgrass_enabled", "0" if tgrass_enabled() else "1")
        await call.answer("Изменено")
        await call.message.edit_text(
            f"🌿 <b>Tgrass</b>",
            reply_markup=op_service_detail_kb("tgrass", tgrass_enabled()))
        return
    if call.data in ("os_tgrass_entry", "os_tgrass_wd"):
        await state.update_data(os_service="tgrass",
                                os_field="entry" if call.data.endswith("entry") else "wd")
        await call.message.answer(f"Введи число (лимит {('входа' if call.data.endswith('entry') else 'вывода')}):")
        await state.set_state(OSDetailEdit.waiting_value)
        return


@dp.callback_query(F.data.startswith("os_traffy"))
async def os_traffy_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    if call.data == "os_traffy":
        await call.message.edit_text(
            f"📊 <b>Traffy</b>\n\n"
            f"Вход: <b>{get_setting('traffy_entry_count')}</b>\n"
            f"Вывод: <b>{get_setting('traffy_withdraw_count')}</b>",
            reply_markup=op_service_detail_kb("traffy", traffy_enabled()),
            parse_mode="HTML")
        return
    if call.data == "os_traffy_toggle":
        set_setting("traffy_enabled", "0" if traffy_enabled() else "1")
        await call.answer("Изменено")
        await call.message.edit_text(
            f"📊 <b>Traffy</b>",
            reply_markup=op_service_detail_kb("traffy", traffy_enabled()))
        return
    if call.data in ("os_traffy_entry", "os_traffy_wd"):
        await state.update_data(os_service="traffy",
                                os_field="entry" if call.data.endswith("entry") else "wd")
        await call.message.answer(f"Введи число (лимит {('входа' if call.data.endswith('entry') else 'вывода')}):")
        await state.set_state(OSDetailEdit.waiting_value)
        return


@dp.message(OSDetailEdit.waiting_value)
async def os_save_value(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
        if val < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число ≥ 1.")
        return
    data = await state.get_data()
    service = data.get("os_service")
    field = data.get("os_field")
    key = f"{service}_{'entry_count' if field == 'entry' else 'withdraw_count'}"
    set_setting(key, val)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key} = {val}", reply_markup=back_admin_kb())


# ---------- API-КЛЮЧИ ----------
def _api_keys_text():
    return (
        f"🔑 <b>API-ключи</b>\n\n"
        f"🌿 Tgrass: <code>{(get_setting('tgrass_api_key') or '—')[:20]}</code>\n"
        f"📊 Traffy: <code>{(get_setting('traffy_api_key') or '—')[:20]}</code>\n"
        f"🎯 PiarFlow: <code>{(get_setting('piarflow_key') or '—')[:20]}</code>"
    )


@dp.callback_query(F.data == "api_keys")
async def api_keys_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        await call.message.edit_text(_api_keys_text(), reply_markup=api_keys_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(_api_keys_text(), reply_markup=api_keys_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("key_"))
async def key_edit_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    service = call.data.split("_", 1)[1]
    key_map = {
        "tgrass": "tgrass_api_key",
        "traffy": "traffy_api_key",
        "piarflow": "piarflow_key",
    }
    if service not in key_map:
        return
    await state.update_data(key_name=key_map[service])
    await call.message.answer(f"🔑 Пришли новый ключ для <b>{service}</b>:", parse_mode="HTML")
    await state.set_state(APIKeyEdit.waiting_key)


@dp.message(APIKeyEdit.waiting_key)
async def key_save_cb(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    key_name = data.get("key_name")
    if not key_name:
        await state.clear()
        return
    set_setting(key_name, message.text.strip())
    await state.clear()
    await message.answer(f"✅ Сохранено: <code>{key_name}</code>", parse_mode="HTML",
                         reply_markup=back_admin_kb())


# ---------- ЗАДАНИЯ PIARFLOW ----------
def tasks_menu_text():
    enabled = piarflow_enabled()
    key = get_setting("piarflow_key") or ""
    return (
        f"🎯 <b>Задания (PiarFlow)</b>\n\n"
        f"Статус: {'🟢 включены' if enabled else '🔴 выключены'}\n"
        f"🔑 Ключ: <code>{key[:12] if key else '—'}</code>\n\n"
        f"💰 Награда за задание: <b>{get_setting('task_reward')}</b> ⭐"
    )


@dp.callback_query(F.data == "tasks_menu")
async def tasks_admin_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(tasks_menu_text(), reply_markup=tasks_kb(piarflow_enabled()), parse_mode="HTML")


@dp.callback_query(F.data == "tasks_toggle")
async def tasks_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = piarflow_enabled()
    set_setting("piarflow_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(tasks_menu_text(), reply_markup=tasks_kb(not current), parse_mode="HTML")


@dp.callback_query(F.data == "tasks_edit_reward")
async def tasks_edit_reward(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💰 Сколько звёзд давать за задание?")
    await state.set_state(TasksEdit.waiting_reward)


@dp.message(TasksEdit.waiting_reward)
async def tasks_save_reward(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("task_reward", val)
    await state.clear()
    await message.answer(f"✅ Награда: {val} ⭐", reply_markup=back_admin_kb())


# ---------- ЗАЯВКИ ----------
async def _render_wd_page(target, idx, edit=False):
    rows = get_pending_withdrawals_all()
    total = len(rows)

    if total == 0:
        text = "📭 Нет активных заявок"
        kb = wd_empty_kb()
        if edit and isinstance(target, CallbackQuery):
            try:
                await target.message.edit_text(text, reply_markup=kb)
                return
            except Exception:
                pass
        if isinstance(target, CallbackQuery):
            await target.message.answer(text, reply_markup=kb)
        else:
            await target.answer(text, reply_markup=kb)
        return

    if idx < 0:
        idx = 0
    if idx >= total:
        idx = total - 1

    wid, user_id, amount, gift_key = rows[idx]
    name = GIFTS.get(gift_key, ("—", 0))[0]
    u = get_user(user_id)
    uname = f"@{u[1]}" if u and u[1] else "без username"

    text = (
        f"💸 <b>Заявка #{wid}</b>\n\n"
        f"👤 {uname}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🎁 {name}\n"
        f"💰 {amount} ⭐\n\n"
        f"📋 Всего активных: <b>{total}</b>"
    )
    kb = wd_page_kb(wid, idx, total)

    if edit and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "wd_list")
async def wd_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await _render_wd_page(call, 0, edit=True)


@dp.callback_query(F.data == "wd_noop")
async def wd_noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data.startswith("wd_page:"))
async def wd_page(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        idx = int(call.data.split(":")[1])
    except Exception:
        idx = 0
    await call.answer()
    await _render_wd_page(call, idx, edit=True)


@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
    set_withdrawal_status(wid, "completed")
    name = GIFTS.get(gift_key, ("подарок", 0))[0]
    try:
        await bot.send_message(user_id,
            f"✅ <b>Заявка #{wid} одобрена!</b>\n\n🎁 {name} отправлен тебе.",
            parse_mode="HTML")
    except Exception:
        pass
    await call.answer("✅ Одобрено")
    await _render_wd_page(call, 0, edit=True)


@dp.callback_query(F.data.startswith("wd_no:"))
async def wd_no(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
    set_withdrawal_status(wid, "rejected")
    add_balance(user_id, amount)
    try:
        await bot.send_message(user_id, f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены.")
    except Exception:
        pass
    await call.answer("❌ Отклонено")
    await _render_wd_page(call, 0, edit=True)


@dp.callback_query(F.data == "wd_accept_all")
async def wd_accept_all(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = accept_all_pending()
    n = len(rows)
    for wid, user_id, amount, gift_key in rows:
        name = GIFTS.get(gift_key, ("подарок", 0))[0]
        try:
            await bot.send_message(user_id,
                f"✅ <b>Заявка #{wid} одобрена!</b>\n\n🎁 {name} отправлен тебе.",
                parse_mode="HTML")
        except Exception:
            pass
    await call.answer(f"✅ Принято: {n}")
    await _render_wd_page(call, 0, edit=True)


@dp.callback_query(F.data == "wd_reject_all")
async def wd_reject_all(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = reject_all_pending()
    n = len(rows)
    for wid, user_id, amount, gift_key in rows:
        try:
            await bot.send_message(user_id,
                f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены.")
        except Exception:
            pass
    await call.answer(f"❌ Отклонено: {n}")
    await _render_wd_page(call, 0, edit=True)


# ---------- ПРИВАТКА ----------
@dp.callback_query(F.data == "priv_menu")
async def priv_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    enabled = get_setting("priv_enabled") == "1"
    text = (
        f"🎛 <b>Приватка</b>\n\n"
        f"Статус: {'🟢 включена' if enabled else '🔴 выключена'}\n\n"
        f"<b>Текст:</b>\n{get_setting('priv_text')}\n\n"
        f"<b>Кнопки:</b>\n{get_setting('priv_buttons')}"
    )
    await call.message.edit_text(text, reply_markup=priv_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "priv_edit_text")
async def priv_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли новый текст приватки:")
    await state.set_state(PrivEdit.waiting_text)


@dp.message(PrivEdit.waiting_text)
async def priv_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("priv_text", _smart_text(message))
    set_setting("priv_enabled", "1")
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "priv_edit_buttons")
async def priv_edit_buttons(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔗 Пришли кнопки:\n\n<b>Столбиком:</b>\n"
        "<code>Кнопка - https://t.me/xxx\nКнопка 2 - https://t.me/yyy</code>\n\n"
        "<b>В ряд:</b>\n<code>К1 - https://t.me/x & К2 - https://t.me/y</code>",
        parse_mode="HTML")
    await state.set_state(PrivEdit.waiting_buttons)


@dp.message(PrivEdit.waiting_buttons)
async def priv_save_buttons(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    ok = False
    for line in text.split("\n"):
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " in pair:
                parts = pair.split(" - ", 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip().startswith("http"):
                    ok = True
    if not ok:
        await message.answer("⚠️ Неверный формат.")
        return
    set_setting("priv_buttons", text)
    set_setting("priv_enabled", "1")
    await state.clear()
    await message.answer("✅ Кнопки сохранены", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "priv_delete")
async def priv_delete(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    set_setting("priv_enabled", "0")
    await call.answer("🗑 Удалено")
    await call.message.edit_text("🗑 Приватка удалена", reply_markup=back_admin_kb())


# ---------- ПОЛЬЗОВАТЕЛЬ (объединяет Юзер + Начислить) ----------
@dp.callback_query(F.data == "user_find")
async def user_find(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("👤 Пришли ID юзера:")
    await state.set_state(UserManage.waiting_id)


@dp.message(UserManage.waiting_id)
async def user_show(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    if not text.lstrip("-").isdigit() or int(text) <= 0:
        await message.answer("⚠️ ID — положительное число.")
        return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Не найден.")
        return
    balance = u[2]
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    reg = (u[5] or "")[:16].replace("T", " ")
    await state.clear()
    await message.answer(
        f"👤 <b>Пользователь</b>\n\n🧑 @{u[1] or '—'}\n🆔 <code>{uid}</code>\n"
        f"⭐ Баланс: <b>{balance}</b>\n👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n📅 Регистрация: {reg}",
        reply_markup=user_manage_kb(uid), parse_mode="HTML")


@dp.callback_query(F.data.startswith("um_add:") | F.data.startswith("um_sub:"))
async def user_manage_amount(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    action, uid_str = call.data.split(":", 1)
    try:
        uid = int(uid_str)
    except Exception:
        return
    sign = "+" if action == "um_add" else "−"
    await state.update_data(um_uid=uid, um_sign=1 if action == "um_add" else -1)
    await call.message.answer(f"{sign} Введи сумму для юзера <code>{uid}</code>:",
                              parse_mode="HTML")
    await state.set_state(UserManage.waiting_amount)


@dp.message(UserManage.waiting_amount)
async def user_manage_save(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text.strip())
        if amount < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно целое число ≥ 1.")
        return
    data = await state.get_data()
    uid = data.get("um_uid")
    sign = data.get("um_sign", 1)
    if not uid:
        await state.clear()
        return
    add_balance(uid, sign * amount)
    new_balance = get_balance(uid)
    await state.clear()
    await message.answer(
        f"✅ {'+' if sign > 0 else '−'}{amount} ⭐\n🆔 <code>{uid}</code>\n"
        f"💰 Баланс: <b>{new_balance}</b> ⭐",
        reply_markup=back_admin_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("user_refs:"))
async def user_refs(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    uid = int(call.data.split(":")[1])
    rows = get_user_referrals(uid, 100)
    if not rows:
        await call.answer("Пусто")
        return
    text = f"👥 <b>Рефералы <code>{uid}</code></b>\n\n"
    icons = {"confirmed": "✅", "pending": "⏳", "expired": "❌"}
    for r_uid, r_name, r_date, r_status in rows:
        icon = icons.get(r_status, "•")
        date = (r_date or "")[:10]
        name = f"@{r_name}" if r_name else "аноним"
        text += f"{icon} {name} — <code>{r_uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


# ---------- СТАТИСТИКА ----------
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    top_bal = get_top_balance(10)
    top_refs = get_top_refs(10)

    t_all = get_task_stats()
    t_today = get_task_stats("today")
    t_week = get_task_stats("week")
    t_month = get_task_stats("month")

    medals = ["🥇", "🥈", "🥉"]
    bal_lines = ""
    for i, (uid, uname, bal) in enumerate(top_bal, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        bal_lines += f"{prefix} {name} — <b>{bal}</b> ⭐\n"

    ref_lines = ""
    for i, (uid, uname, refs) in enumerate(top_refs, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        ref_lines += f"{prefix} {name} — <b>{refs}</b> 👥\n"

    text = (
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Всего юзеров: <b>{s['total']}</b>\n"
        f"📅 Новых сегодня: <b>{s['today']}</b>\n"
        f"💰 Общий баланс: <b>{s['total_balance']}</b> ⭐\n"
        f"👥 Подтверждённых рефералов: <b>{s['total_refs']}</b>\n\n"
        f"✅ <b>ЗАДАНИЯ (все сервисы):</b>\n"
        f"   Всего: <b>{t_all['count']}</b> (уник. {t_all['unique_users']})\n"
        f"   За сегодня: <b>{t_today['count']}</b>\n"
        f"   За неделю: <b>{t_week['count']}</b>\n"
        f"   За месяц: <b>{t_month['count']}</b>\n"
        f"   Выдано звёзд: <b>{t_all['stars']}</b> ⭐\n\n"
        f"📋 <b>Заявки на вывод:</b>\n"
        f"   ⏳ В ожидании: <b>{s['pending']}</b>\n"
        f"   ✅ Выполнено: <b>{s['done']}</b>\n"
        f"   ❌ Отклонено: <b>{s['rejected']}</b>\n"
        f"   💫 Выдано звёзд: <b>{s['total_stars']}</b>\n\n"
        f"🏆 <b>Топ-10 по балансу:</b>\n{bal_lines or '   —'}\n"
        f"👥 <b>Топ-10 по рефералам:</b>\n{ref_lines or '   —'}"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    try:
        await call.message.edit_text(text, reply_markup=stats_kb(), parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer(text, reply_markup=stats_kb(), parse_mode="HTML")
        except Exception:
            pass


# ---------- НАСТРОЙКИ ----------
@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"👥 Бонус за реферала: <b>{get_setting('ref_bonus')}</b> ⭐\n"
        f"🎁 Ежедневный бонус: <b>{get_setting('daily_bonus')}</b> ⭐\n"
        f"💸 Минимум вывода: <b>{get_setting('min_withdraw')}</b> ⭐\n"
        f"🎉 Бонус за /start: <b>{get_setting('welcome_bonus')}</b> ⭐\n"
        f"👥 Друзей для вывода: <b>{get_setting('withdraw_friends_required')}</b>\n"
        f"✏️ Текст под меню: {get_setting('welcome_text')}",
        reply_markup=settings_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("set:"))
async def set_value_ask(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    key = call.data.split(":")[1]
    prompts = {
        "ref_bonus": "👥 Бонус за реферала (число):",
        "daily_bonus": "🎁 Ежедневный бонус (число):",
        "min_withdraw": "💸 Минимум вывода (число):",
        "welcome_bonus": "🎉 Бонус за /start (число):",
        "withdraw_friends_required": "👥 Сколько друзей нужно для вывода?",
        "welcome_text": "✏️ Текст под меню:",
    }
    if key not in prompts:
        return
    await state.update_data(set_key=key)
    await call.message.answer(prompts[key])
    await state.set_state(SetValue.waiting_value)


@dp.message(SetValue.waiting_value)
async def set_value_save(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    key = data.get("set_key")
    value = message.text.strip()
    if key in ("ref_bonus", "daily_bonus", "min_withdraw",
               "welcome_bonus", "withdraw_friends_required"):
        try:
            int(value)
        except Exception:
            await message.answer("⚠️ Нужно число.")
            return
    set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key}", reply_markup=back_admin_kb())


# ---------- ПРОМОКОДЫ ----------
@dp.callback_query(F.data == "promos")
async def promos(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=promos_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "promo_create")
async def promo_create(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    code = "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    await state.update_data(code=code)
    await call.message.answer(
        f"🎟 Код: <code>{code}</code>\n\n"
        f"💰 Введи <b>от</b> сколько звёзд (минимум):",
        parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount_min)


@dp.message(PromoCreate.waiting_amount_min)
async def promo_amount_min_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount_min = int(message.text.strip())
        if amount_min < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число ≥ 1.")
        return
    await state.update_data(amount_min=amount_min)
    await message.answer(f"💰 Введи <b>до</b> сколько звёзд (максимум, ≥ {amount_min}):",
                         parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount_max)


@dp.message(PromoCreate.waiting_amount_max)
async def promo_amount_max_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount_max = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    data = await state.get_data()
    amount_min = data.get("amount_min", 1)
    if amount_max < amount_min:
        await message.answer(f"⚠️ Максимум должен быть ≥ {amount_min}.")
        return
    await state.update_data(amount_max=amount_max)
    await message.answer("🎯 Сколько активаций?")
    await state.set_state(PromoCreate.waiting_uses)


@dp.message(PromoCreate.waiting_uses)
async def promo_uses_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uses = int(message.text.strip())
        if uses < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число ≥ 1.")
        return

    data = await state.get_data()
    code = data["code"]
    amount_min = data["amount_min"]
    amount_max = data["amount_max"]

    create_promo(code, amount_max, uses, amount_min=amount_min)
    await state.clear()

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=promo_{code}"

    if amount_min == amount_max:
        sum_line = f"{amount_max} ⭐"
    else:
        sum_line = f"{amount_min}-{amount_max} ⭐ (рандом)"

    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎟 Код: <code>{code}</code>\n"
        f"💰 Сумма: <b>{sum_line}</b>\n"
        f"🎯 Активаций: <b>{uses}</b>\n\n"
        f"🔗 <b>Ссылка для юзеров:</b>\n"
        f"<code>{link}</code>",
        parse_mode="HTML",
        reply_markup=back_admin_kb())


@dp.callback_query(F.data == "promo_list")
async def promo_list_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_promos()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    await call.message.edit_text(
        "📜 <b>Промокоды</b>\n\nНажми на промокод, чтобы увидеть статистику:",
        reply_markup=promo_list_kb(rows), parse_mode="HTML")


@dp.callback_query(F.data.startswith("promo_view:"))
async def promo_view_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    code = call.data.split(":", 1)[1]
    promo = get_promo(code)
    if not promo:
        await call.answer("Не найден", show_alert=True)
        return
    c, amount, mx, used, active, amount_min = promo
    uses_list = get_promo_uses_list(code, 10)

    if amount_min and amount_min < amount:
        sum_line = f"{amount_min}-{amount} ⭐ (рандом)"
        avg = (amount + amount_min) // 2
    else:
        sum_line = f"{amount} ⭐"
        avg = amount
    total_given = used * avg

    text = (
        f'<tg-emoji emoji-id="5203993413346680064">📊</tg-emoji> <b>Промокод</b> <code>{code}</code>\n\n'
        f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> Сумма: <b>{sum_line}</b>\n'
        f'<tg-emoji emoji-id="5350460637182993292">🎯</tg-emoji> Активаций: <b>{used} / {mx}</b>\n'
        f'<tg-emoji emoji-id="5895708410447401643">⭐</tg-emoji> Выдано звёзд (≈): <b>{total_given}</b>\n\n'
    )
    if uses_list:
        text += "<b>Последние активации:</b>\n"
        for uid, uname, used_at in uses_list:
            name = f"@{uname}" if uname else f"ID {uid}"
            date = (used_at or "")[:16].replace("T", " ")
            text += f"• {name} — {date}\n"
    else:
        text += "<i>Ещё никто не активировал.</i>"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"

    try:
        await call.message.edit_text(text, reply_markup=promo_view_kb(code), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data.startswith("promo_del_confirm:"))
async def promo_del_confirm(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    code = call.data.split(":", 1)[1]
    delete_promo(code)
    await call.answer(f"🗑 {code} удалён")
    rows = list_promos()
    if not rows:
        try:
            await call.message.edit_text("📜 <b>Список пуст</b>",
                                          reply_markup=promos_kb(), parse_mode="HTML")
        except Exception:
            pass
        return
    try:
        await call.message.edit_text(
            "📜 <b>Промокоды</b>\n\nНажми на промокод, чтобы увидеть статистику:",
            reply_markup=promo_list_kb(rows), parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "promo_delete")
async def promo_delete_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Код для удаления:")
    await state.set_state(PromoDelete.waiting_code)


@dp.message(PromoDelete.waiting_code)
async def promo_delete_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not get_promo(code):
        await message.answer("⚠️ Нет такого.")
        return
    delete_promo(code)
    await state.clear()
    await message.answer(f"🗑 Удалён <code>{code}</code>", parse_mode="HTML")


# ---------- РЕКЛАМА ----------
@dp.callback_query(F.data == "ad_menu")
async def ad_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📊 <b>Реклама</b>\n\n"
        "Создай метку, дай рекламодателю ссылку <code>?start=ad_КОД</code>.\n"
        "Он сможет смотреть статистику командой <code>/stat_КОД</code>.",
        reply_markup=ad_menu_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "ad_add")
async def ad_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "📝 Пришли код метки (латиница, цифры, _), например: <code>nikita</code>",
        parse_mode="HTML")
    await state.set_state(AdAdd.waiting_code)


@dp.message(AdAdd.waiting_code)
async def ad_code_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().lower()
    if not code.replace("_", "").isalnum() or len(code) < 3:
        await message.answer("⚠️ Только латиница/цифры/_, минимум 3.")
        return
    if get_ad_source(code):
        await message.answer("⚠️ Такая метка уже есть.")
        return
    await state.update_data(ad_code=code)
    await message.answer(
        "👤 Пришли <code>@username</code> или <code>user_id</code> рекламодателя:",
        parse_mode="HTML")
    await state.set_state(AdAdd.waiting_owner)


@dp.message(AdAdd.waiting_owner)
async def ad_owner_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip()
    owner_id = None
    owner_username = ""
    if raw.lstrip("-").isdigit():
        owner_id = int(raw)
        u = get_user(owner_id)
        if u and u[1]:
            owner_username = u[1]
    elif raw.startswith("@"):
        uname = raw[1:]
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE username = ?", (uname,))
        r = cur.fetchone()
        conn.close()
        if not r:
            await message.answer("⚠️ Юзер с таким @username не найден.")
            return
        owner_id = r[0]
        owner_username = uname
    else:
        await message.answer("⚠️ Пришли @username или user_id.")
        return

    await state.update_data(ad_owner_id=owner_id, ad_owner_username=owner_username)
    await message.answer("💰 Цена за переход в рублях (целое число, 0 если не надо):")
    await state.set_state(AdAdd.waiting_price)


@dp.message(AdAdd.waiting_price)
async def ad_price_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        price = int(message.text.strip())
        if price < 0:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число ≥ 0.")
        return

    data = await state.get_data()
    code = data.get("ad_code")
    owner_id = data.get("ad_owner_id")
    owner_username = data.get("ad_owner_username", "")

    add_ad_source(code, owner_id, owner_username, price_per_click=price)
    await state.clear()

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ad_{code}"
    await message.answer(
        f"✅ Метка <code>{code}</code> создана.\n\n"
        f"👤 Владелец: <code>{owner_id}</code> (@{owner_username or '—'})\n"
        f"💰 Цена перехода: <b>{price}</b> ₽\n"
        f"🔗 Ссылка: <code>{link}</code>\n\n"
        f"Пусть рекламодатель зайдёт и напишет <code>/stat_{code}</code>",
        parse_mode="HTML")


@dp.callback_query(F.data == "ad_list")
async def ad_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_ad_sources()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    me = await bot.get_me()
    text = "📜 <b>Метки</b>\n\n"
    for row in rows:
        code = row[0]
        owner_id = row[1]
        owner_username = row[2]
        price = row[5] if len(row) > 5 else 0
        link = f"https://t.me/{me.username}?start=ad_{code}"
        text += (f"<code>{code}</code> — <code>{owner_id}</code> (@{owner_username or '—'}) — "
                 f"<b>{price}</b> ₽\n{link}\n\n")
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "ad_del")
async def ad_del_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Пришли код метки для удаления:")
    await state.set_state(AdDel.waiting_code)


@dp.message(AdDel.waiting_code)
async def ad_del_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().lower()
    if not get_ad_source(code):
        await message.answer("⚠️ Нет такой.")
        return
    delete_ad_source(code)
    await state.clear()
    await message.answer(f"🗑 Удалено <code>{code}</code>", parse_mode="HTML")


# ---------- РАССЫЛКА ----------
BROADCAST_STATE = {}


def _get_broadcast_state():
    return BROADCAST_STATE.setdefault(ADMIN_ID, {})


def broadcast_menu_text():
    b = _get_broadcast_state()
    mtype = b.get("media_type")
    if mtype == "photo":
        media = "🖼 фото"
    elif mtype == "sticker":
        media = "🎨 стикер"
    elif mtype == "video":
        media = "🎬 видео"
    else:
        media = "нет"
    count = b.get("count") or get_setting("broadcast_batch_default") or "всем"
    btns = "есть" if b.get("buttons") else "нет"
    text_prev = (b.get("text") or "—")[:60]
    return (
        f"📢 <b>Рассылка</b>\n\n"
        f"📝 Текст: {text_prev}...\n"
        f"📎 Медиа: <b>{media}</b>\n"
        f"🔗 Кнопки: <b>{btns}</b>\n"
        f"👥 Количество: <b>{count}</b>"
    )


@dp.callback_query(F.data == "broadcast_menu")
async def broadcast_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    try:
        await call.message.edit_text(broadcast_menu_text(),
                                      reply_markup=broadcast_menu_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(broadcast_menu_text(),
                                  reply_markup=broadcast_menu_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "bc_edit_text")
async def bc_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли текст рассылки:")
    await state.set_state(BroadcastFlow.waiting_text)


@dp.message(BroadcastFlow.waiting_text)
async def bc_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    _get_broadcast_state()["text"] = _smart_text(message)
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_media_add")
async def bc_media_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "📎 Пришли фото, стикер или видео одним сообщением:\n"
        "Бот сам определит тип.")
    await state.set_state(BroadcastFlow.waiting_media)


@dp.message(BroadcastFlow.waiting_media)
async def bc_save_media(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    if message.photo:
        b["media_type"] = "photo"
        b["media_id"] = message.photo[-1].file_id
    elif message.sticker:
        b["media_type"] = "sticker"
        b["media_id"] = message.sticker.file_id
    elif message.video:
        b["media_type"] = "video"
        b["media_id"] = message.video.file_id
    else:
        await message.answer("⚠️ Нужно фото, стикер или видео.")
        return
    await state.clear()
    await message.answer("✅ Медиа сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_media_del")
async def bc_media_del(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    b.pop("media_id", None)
    b.pop("media_type", None)
    await call.answer("🗑 Убрано")
    try:
        await call.message.edit_text(broadcast_menu_text(),
                                      reply_markup=broadcast_menu_kb(), parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "bc_edit_buttons")
async def bc_edit_buttons(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔗 Пришли кнопки (по одной в строке, или через & для ряда):\n\n"
        "<code>Кнопка - https://t.me/xxx - 5258057130228849960</code>\n"
        "Третий параметр (ID эмодзи) — опционально.\n\n"
        "Очистить — пришли <code>-</code>",
        parse_mode="HTML")
    await state.set_state(BroadcastFlow.waiting_buttons)


@dp.message(BroadcastFlow.waiting_buttons)
async def bc_save_buttons(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    if text == "-":
        _get_broadcast_state().pop("buttons", None)
        await state.clear()
        await message.answer("🗑 Очищено", reply_markup=back_admin_kb())
        return
    _get_broadcast_state()["buttons"] = text
    await state.clear()
    await message.answer("✅ Кнопки сохранены", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_edit_count")
async def bc_edit_count(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    users = get_all_user_ids()
    await call.message.answer(
        f"👥 Сколько отправить? Всего: <b>{len(users)}</b>\n\n"
        f"Пришли число (например 10000) или <code>all</code> — всем.",
        parse_mode="HTML")
    await state.set_state(BroadcastFlow.waiting_count)


@dp.message(BroadcastFlow.waiting_count)
async def bc_save_count(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip().lower()
    if raw == "all":
        _get_broadcast_state()["count"] = 0
        await state.clear()
        await message.answer("✅ Всем", reply_markup=back_admin_kb())
        return
    try:
        val = int(raw)
        if val < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число или all.")
        return
    _get_broadcast_state()["count"] = val
    await state.clear()
    await message.answer(f"✅ Отправить {val}", reply_markup=back_admin_kb())


def _build_bc_kb():
    raw = _get_broadcast_state().get("buttons")
    if not raw:
        return None
    rows = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        row = []
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " not in pair:
                continue
            parts = [p.strip() for p in pair.split(" - ")]
            if len(parts) < 2:
                continue
            text = parts[0]
            url = parts[1]
            emoji_id = parts[2] if len(parts) >= 3 else ""
            if not text or not url:
                continue
            if emoji_id:
                row.append(InlineKeyboardButton(text=text, url=url,
                                                icon_custom_emoji_id=emoji_id))
            else:
                row.append(InlineKeyboardButton(text=text, url=url))
        if row:
            rows.append(row)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_broadcast_to(uid, b, kb):
    mtype = b.get("media_type")
    mid = b.get("media_id")
    text = b.get("text")

    if mtype == "photo" and mid:
        await bot.send_photo(uid, mid, caption=text or None,
                             reply_markup=kb, parse_mode="HTML" if text else None)
        return True
    if mtype == "video" and mid:
        await bot.send_video(uid, mid, caption=text or None,
                             reply_markup=kb, parse_mode="HTML" if text else None)
        return True
    if mtype == "sticker" and mid:
        await bot.send_sticker(uid, mid, reply_markup=kb)
        if text:
            try:
                await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass
        return True
    if not text:
        raise ValueError("no text and no media")
    await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
    return True


@dp.callback_query(F.data == "bc_preview")
async def bc_preview(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    mtype = b.get("media_type")
    mid = b.get("media_id")
    text = b.get("text")
    if not text and not (mtype and mid):
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    kb = _build_bc_kb()
    try:
        await _send_broadcast_to(call.from_user.id, b, kb)
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка: {e}")
    await call.message.answer("👁 Предпросмотр готов.", reply_markup=broadcast_preview_kb())


@dp.callback_query(F.data == "bc_send")
async def bc_send(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    if not b.get("text") and not b.get("media_id"):
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    await call.message.edit_text(
        "📢 Проверь предпросмотр выше и нажми кнопку:",
        reply_markup=broadcast_confirm_kb())


@dp.callback_query(F.data == "bc_start")
async def bc_start(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    count = b.get("count") or 0
    if not b.get("text") and not b.get("media_id"):
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    kb = _build_bc_kb()

    users = get_all_user_ids()
    if count and count < len(users):
        users = users[:count]

    total = len(users)
    await call.message.edit_text(f"📢 Начинаю... (0/{total})")

    sent = 0
    errors = 0
    blocked = 0
    for i, uid in enumerate(users, 1):
        try:
            await _send_broadcast_to(uid, b, kb)
            sent += 1
        except Exception as e:
            es = str(e).lower()
            if "parse entities" in es or "unclosed" in es or "can't parse" in es:
                try:
                    mtype = b.get("media_type")
                    mid = b.get("media_id")
                    text = b.get("text")
                    if mtype == "photo" and mid:
                        await bot.send_photo(uid, mid, caption=text, reply_markup=kb)
                    elif mtype == "video" and mid:
                        await bot.send_video(uid, mid, caption=text, reply_markup=kb)
                    elif mtype == "sticker" and mid:
                        await bot.send_sticker(uid, mid, reply_markup=kb)
                    else:
                        await bot.send_message(uid, text, reply_markup=kb)
                    sent += 1
                    continue
                except Exception as e2:
                    print(f"bc fallback: {e2}")
            errors += 1
            if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
                blocked += 1
                mark_ad_user_blocked(uid)
        if i % 30 == 0:
            try:
                await call.message.edit_text(f"📢 Рассылка... ({i}/{total})")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    try:
        await call.message.edit_text(
            f"✅ Готово!\n\n"
            f"📤 Отправлено: <b>{sent}</b>\n"
            f"🚫 Заблокировали: <b>{blocked}</b>\n"
            f"❌ Ошибок: <b>{errors}</b>",
            parse_mode="HTML",
            reply_markup=back_admin_kb())
    except Exception:
        pass
    BROADCAST_STATE[ADMIN_ID] = {}


# ---------- БЭКАП ----------
@dp.callback_query(F.data == "backup_help")
async def backup_help(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📦 <b>Бэкап</b>\n\n"
        "📤 <b>Выгрузка:</b> <code>/backup</code>.\n\n"
        "📥 <b>Загрузка:</b> отправь боту JSON-файл.\n\n"
        "🤖 Авто-бэкап: 8:00 и 20:00.",
        reply_markup=back_admin_kb(), parse_mode="HTML")


@dp.message(Command("backup"))
async def backup_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📦 Собираю бэкап...")
    data = export_users_to_json()
    fname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        file = FSInputFile(fname)
        await message.answer_document(file, caption=(
            f"📦 <b>Бэкап</b>\n\n"
            f"👥 Юзеров: <b>{len(data['users'])}</b>\n"
            f"✅ Заданий: <b>{len(data.get('task_completed', []))}</b>\n"
            f"🎟 Промокодов: <b>{len(data['promos'])}</b>"), parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    try:
        os.remove(fname)
    except Exception:
        pass


@dp.message(F.document)
async def restore_doc(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    doc = message.document
    if not doc.file_name.endswith(".json"):
        return
    try:
        file = await bot.get_file(doc.file_id)
        fname = f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await bot.download_file(file.file_path, fname)
        with open(fname, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = import_users_from_json(data)
        try:
            os.remove(fname)
        except Exception:
            pass
        await message.answer(f"✅ <b>Восстановлено</b>\n\n👥 Юзеров: <b>{count}</b>",
                             parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ================== ФОН: РЕФЕРАЛЬНЫЙ ВОРКЕР ==================
async def referral_watcher():
    while True:
        try:
            for rid, user_id, referrer_id in get_refs_to_remind():
                u = get_user(user_id)
                uname = f"@{u[1]}" if u and u[1] else "друг"
                try:
                    await bot.send_message(referrer_id,
                        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> '
                        f'{uname} зашёл по твоей ссылке, но не забрал бонус.',
                        parse_mode="HTML")
                except Exception:
                    pass
                mark_reminded(rid)

            expired = expire_old_referrals()
            if expired:
                grouped = {}
                for user_id, referrer_id in expired:
                    grouped.setdefault(referrer_id, []).append(user_id)
                for referrer_id, users in grouped.items():
                    lines = "\n".join([f"• ID <code>{uid}</code>" for uid in users])
                    try:
                        await bot.send_message(referrer_id,
                            f'<tg-emoji emoji-id="5787192063099408213">🕗</tg-emoji> '
                            f'<b>Прошло {REFERRAL_DAYS} дней.</b>\n'
                            f'Друзья не забрали бонус:\n{lines}',
                            parse_mode="HTML")
                    except Exception:
                        pass
        except Exception as e:
            print("Watcher error:", e)
        await asyncio.sleep(60)


# ================== ФОН: N ДРУЗЕЙ ==================
async def withdraw_watcher():
    while True:
        try:
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            cur.execute("SELECT user_id, gift_key FROM withdraw_waiting")
            rows = cur.fetchall()
            conn.close()
            for user_id, gift_key in rows:
                try:
                    await _check_and_fulfill_waiting(user_id)
                except Exception as e:
                    print(f"withdraw_watcher {user_id}: {e}")
        except Exception as e:
            print("withdraw_watcher error:", e)
        await asyncio.sleep(60)


# ================== ФОН: АВТО-БЭКАП ==================
async def daily_backup():
    while True:
        try:
            now = datetime.now()
            targets = [
                now.replace(hour=8, minute=0, second=0, microsecond=0),
                now.replace(hour=20, minute=0, second=0, microsecond=0),
            ]
            next_run = None
            for t in targets:
                if t > now:
                    next_run = t
                    break
            if next_run is None:
                next_run = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
            wait_seconds = (next_run - now).total_seconds()
            print(f"Авто-бэкап: следующий через {int(wait_seconds)} сек ({next_run.strftime('%H:%M')})")
            await asyncio.sleep(wait_seconds)

            data = export_users_to_json()
            fname = f"backup_{datetime.now().strftime('%Y%m%dстави_%H%M%S')}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                file = FSInputFile(fname)
                await bot.send_document(
                    ADMIN_ID, file,
                    caption=(f"📦 <b>Авто-бэкап</b>\n"
                             f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\nм\n"
                             f"👥 Юзеров: <.
b>{len(data['users'])}</b>"),
                   - parse_mode="HTML")
                print("Авто-бэкап отправлен")
            except Exception as e:
                print("Backup send error:", e)
            try:
                os.remove(fname)
            except Exception:
                pass
        except Exception as e:
            print("daily_backup error:", e)
            await asyncio.sleep(3600)


# ================== ЗАПУСК ==================
async def main():
    init_db()
    _ensure_user_offers_table()
    asyncio.create_task(referral_watcher())
    asyncio.create_task(withdraw_watcher())
    asyncio.create_task(daily_backup())
    print("Бот запущен")
    print(f"BOT_ID: {BOT_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
