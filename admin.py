from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS
from database import (
    get_setting, set_setting, get_sponsors, get_sponsor,
    set_sponsor_key, toggle_sponsor, move_sponsor, get_stats,
)
from keyboards import (
    admin_kb, back_kb, settings_kb, sponsors_kb, sponsor_menu_kb,
)

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

LABELS = {
    "task_reward": "Награда за задание",
    "ref_reward": "Награда за друга",
    "ref_tasks_needed": "Заданий от друга для награды",
    "min_withdraw": "Минимум для вывода",
}


class Form(StatesGroup):
    value = State()
    key = State()


@router.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🛠 Админ-панель", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:back")
async def adm_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛠 Админ-панель", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    users, balance, tasks = await get_stats()
    await call.message.edit_text(
        f"📊 Пользователей: {users}\n"
        f"💰 Общий баланс: {balance:.2f} ⭐\n"
        f"✅ Выполнено заданий: {tasks}",
        reply_markup=back_kb(),
    )


# ---------- настройки ----------

@router.callback_query(F.data == "adm:settings")
async def adm_settings(call: CallbackQuery):
    lines = ["⚙️ Настройки:\n"]
    for k, name in LABELS.items():
        lines.append(f"{name}: {await get_setting(k)}")
    await call.message.edit_text(
        "\n".join(lines), reply_markup=settings_kb(LABELS))


@router.callback_query(F.data.startswith("set:"))
async def set_pick(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    await state.set_state(Form.value)
    await state.update_data(key=key)
    await call.message.edit_text(
        f"Введи новое значение для «{LABELS[key]}» (число):",
        reply_markup=back_kb("adm:settings"),
    )


@router.message(Form.value)
async def set_value(message: Message, state: FSMContext):
    try:
        val = float((message.text or "").replace(",", "."))
        if val < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно число, например 0.25")
        return
    data = await state.get_data()
    key = data["key"]
    if key == "ref_tasks_needed":
        val = int(val)
    await set_setting(key, val)
    await state.clear()
    await message.answer(
        f"✅ {LABELS[key]}: {val}", reply_markup=admin_kb())


# ---------- спонсоры ----------

async def show_sponsors(call: CallbackQuery):
    sponsors = await get_sponsors()
    await call.message.edit_text(
        "🤝 Спонсоры (чем выше, тем раньше показываются).\n"
        "✅ включён, ❌ выключен, 🔑 ключ есть",
        reply_markup=sponsors_kb(sponsors),
    )


async def show_sponsor(call: CallbackQuery, name):
    s = await get_sponsor(name)
    key = s["api_key"]
    shown = (key[:4] + "..." + key[-3:]) if len(key) > 8 else (
        key or "не задан")
    status = "включён" if s["enabled"] else "выключен"
    await call.message.edit_text(
        f"{name}\nСтатус: {status}\nПриоритет: {s['priority']}\n"
        f"Ключ: {shown}",
        reply_markup=sponsor_menu_kb(name, s["enabled"]),
    )


@router.callback_query(F.data == "adm:sponsors")
async def adm_sponsors(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_sponsors(call)


@router.callback_query(F.data.startswith("sp:"))
async def sp_open(call: CallbackQuery):
    await show_sponsor(call, call.data.split(":", 1)[1])


@router.callback_query(F.data.startswith("spt:"))
async def sp_toggle(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    await toggle_sponsor(name)
    await show_sponsor(call, name)


@router.callback_query(F.data.startswith("spu:"))
async def sp_up(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    await move_sponsor(name, up=True)
    await show_sponsor(call, name)


@router.callback_query(F.data.startswith("spd:"))
async def sp_down(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    await move_sponsor(name, up=False)
    await show_sponsor(call, name)


@router.callback_query(F.data.startswith("spx:"))
async def sp_delete_key(call: CallbackQuery):
    name = call.data.split(":", 1)[1]
    await set_sponsor_key(name, "")
    await show_sponsor(call, name)


@router.callback_query(F.data.startswith("spk:"))
async def sp_key_pick(call: CallbackQuery, state: FSMContext):
    name = call.data.split(":", 1)[1]
    await state.set_state(Form.key)
    await state.update_data(name=name)
    await call.message.edit_text(
        f"Отправь API-ключ для {name}:",
        reply_markup=back_kb(f"sp:{name}"),
    )


@router.message(Form.key)
async def sp_key_save(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    await set_sponsor_key(name, (message.text or "").strip())
    await state.clear()
    try:
        await message.delete()  # убираем ключ из чата
    except Exception:
        pass
    await message.answer(
        f"✅ Ключ для {name} сохранён", reply_markup=admin_kb())
