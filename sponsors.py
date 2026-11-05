"""
Подключение сервисов с заданиями: Tgrass, PiarFlow, Flyer, Trafsly, Traffy.

Задание это словарь:
    {"sponsor": "tgrass", "id": "123", "text": "...", "url": "https://...",
     "extra": {...}}

Для каждого сервиса две функции:
    fetch_<имя>(user, api_key) -> список заданий
    check_<имя>(user_id, api_key, task) -> True, если задание выполнено
"""
import aiohttp
from database import get_sponsors, is_task_done

# True, если бот подключён к PiarFlow без токена бота
PIARFLOW_NO_TOKEN = False

current = {}   # user_id -> текущее задание
skipped = {}   # user_id -> {полные id пропущенных заданий}

DEFAULT_TEXT = "Выполни задание и нажми «Подтвердить»"
TYPE_TEXT = {
    "channel": "Подпишись на канал и нажми «Подтвердить»",
    "bot": "Запусти бота и нажми «Подтвердить»",
}
FLYER_TEXT = {
    "subscribe channel": TYPE_TEXT["channel"],
    "start bot": TYPE_TEXT["bot"],
    "give boost": "Дай буст каналу и нажми «Подтвердить»",
    "follow link": "Перейди по ссылке и нажми «Подтвердить»",
    "view posts": "Посмотри посты и нажми «Подтвердить»",
}


def user_info(u):
    """Данные пользователя из aiogram User."""
    return {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name or "",
        "lang": u.language_code or "ru",
        "premium": bool(u.is_premium),
    }


async def _post(url, headers, payload):
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload, headers=headers) as r:
            return await r.json(content_type=None)


def _task(sponsor, tid, text, url, **extra):
    return {"sponsor": sponsor, "id": str(tid), "text": text,
            "url": url, "extra": extra}


# ---------- Tgrass ----------

async def fetch_tgrass(user, key):
    data = await _post(
        "https://tgrass.space/tasks", {"Auth": key},
        {"tg_user_id": user["id"], "tg_login": user["username"],
         "lang": user["lang"], "is_premium": user["premium"]})
    out = []
    for o in data.get("offers") or []:
        if o.get("subscribed"):
            continue
        text = TYPE_TEXT.get(o.get("type"), DEFAULT_TEXT)
        out.append(_task("tgrass", o["offer_id"], text, o.get("link")))
    return out


async def check_tgrass(uid, key, task):
    data = await _post(
        "https://tgrass.space/check", {"Auth": key},
        {"tg_user_id": uid, "offer_id": int(task["id"])})
    return data.get("status") == "subscribed" and not data.get("is_fake")


# ---------- PiarFlow ----------

PF = "https://piarflow.com/v1"


async def fetch_piarflow(user, key):
    payload = {"user_id": user["id"], "chat_id": user["id"],
               "max_sponsors": 5}
    if PIARFLOW_NO_TOKEN:
        payload.update({
            "first_name": user["first_name"], "username": user["username"],
            "language_code": user["lang"], "bio": None})
    data = await _post(
        f"{PF}/sponsors", {"Authorization": f"Bearer {key}"}, payload)
    out = []
    for s in data.get("sponsors") or []:
        if s.get("status") == "subscribed":
            continue
        out.append(_task("piarflow", s["link"], DEFAULT_TEXT, s["link"]))
    return out


async def check_piarflow(uid, key, task):
    data = await _post(
        f"{PF}/sponsors/check", {"Authorization": f"Bearer {key}"},
        {"user_id": uid, "links": [task["url"]]})
    items = data.get("sponsors") or []
    return bool(items) and all(
        i.get("status") == "subscribed" for i in items)


# ---------- Flyer ----------

FL = "https://api.flyerhubs.com"


async def fetch_flyer(user, key):
    data = await _post(
        f"{FL}/get_tasks", {},
        {"key": key, "user_id": user["id"],
         "language_code": user["lang"], "limit": 5})
    out = []
    for t in data.get("result") or []:
        if t.get("status") != "incomplete":
            continue
        links = t.get("links") or []
        text = FLYER_TEXT.get(t.get("task"), DEFAULT_TEXT)
        out.append(_task(
            "flyer", t["signature"], text, links[0] if links else None))
    return out


async def check_flyer(uid, key, task):
    data = await _post(
        f"{FL}/check_task", {}, {"key": key, "signature": task["id"]})
    return data.get("result") in ("complete", "waiting")


# ---------- Trafsly ----------

TS = "https://api.trafsly.com/api/v1"


async def fetch_trafsly(user, key):
    data = await _post(
        f"{TS}/get-sponsors", {"Auth": key},
        {"user_id": user["id"], "first_name": user["first_name"],
         "username": user["username"], "language_code": user["lang"],
         "is_premium": user["premium"]})
    out = []
    for s in data.get("sponsors") or []:
        if s.get("status") in ("subscribed", "notgetted"):
            continue
        text = TYPE_TEXT.get(s.get("type"), DEFAULT_TEXT)
        out.append(_task("trafsly", s["ads_id"], text, s.get("link"),
                         ads_id=s["ads_id"]))
    return out


async def check_trafsly(uid, key, task):
    data = await _post(
        f"{TS}/confirm-subscription", {"Auth": key},
        {"user_id": uid, "ads_id": task["extra"]["ads_id"]})
    return bool(data.get("subscribed"))


# ---------- Traffy ----------

TR = "https://api.traffy.ai/publisher"


async def fetch_traffy(user, key):
    data = await _post(
        f"{TR}/tasks", {"x-publisher-api-key": key},
        {"telegram_id": user["id"], "limit": 5,
         "first_name": user["first_name"], "username": user["username"],
         "language_code": user["lang"]})
    out = []
    for t in data.get("tasks") or []:
        title = t.get("title")
        text = (f"Подпишись на «{title}» и нажми «Подтвердить»"
                if title else DEFAULT_TEXT)
        out.append(_task(
            "traffy", t["assignment_id"], text, t.get("target_link")))
    return out


async def check_traffy(uid, key, task):
    data = await _post(
        f"{TR}/tasks/check", {"x-publisher-api-key": key},
        {"telegram_id": uid, "assignment_ids": [task["id"]]})
    results = data.get("results") or []
    if not results:
        return False
    r = results[0]
    # rewarded=False: вступил не по ссылке задания, награды нет
    return r.get("status") == "completed" and r.get("rewarded") is not False


FETCHERS = {
    "tgrass": fetch_tgrass,
    "piarflow": fetch_piarflow,
    "flyer": fetch_flyer,
    "trafsly": fetch_trafsly,
    "traffy": fetch_traffy,
}

CHECKERS = {
    "tgrass": check_tgrass,
    "piarflow": check_piarflow,
    "flyer": check_flyer,
    "trafsly": check_trafsly,
    "traffy": check_traffy,
}


# ---------- общая логика ----------

def full_id(task):
    return f"{task['sponsor']}:{task['id']}"


async def get_next_task(user):
    """Берёт задание у первого по приоритету включённого спонсора."""
    uid = user["id"]
    exclude = skipped.setdefault(uid, set())
    for s in await get_sponsors(only_active=True):
        fetch = FETCHERS.get(s["name"])
        if not fetch:
            continue
        try:
            tasks = await fetch(user, s["api_key"])
        except Exception as e:
            print(f"[{s['name']}] fetch error: {e}")
            continue
        for task in tasks or []:
            tid = full_id(task)
            if tid in exclude or await is_task_done(uid, tid):
                continue
            current[uid] = task
            return task
    exclude.clear()  # пропущенные снова станут доступны
    current.pop(uid, None)
    return None


async def check_task(user_id, task):
    """True, если пользователь выполнил задание."""
    sponsors = {s["name"]: s for s in await get_sponsors()}
    s = sponsors.get(task["sponsor"])
    check = CHECKERS.get(task["sponsor"])
    if not s or not check or not s["api_key"]:
        return False
    try:
        return bool(await check(user_id, s["api_key"], task))
    except Exception as e:
        print(f"[{task['sponsor']}] check error: {e}")
        return False


def skip_task(user_id):
    task = current.pop(user_id, None)
    if task:
        skipped.setdefault(user_id, set()).add(full_id(task))
