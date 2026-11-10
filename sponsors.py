"""
Сервисы с заданиями: Tgrass, PiarFlow, Flyer, Trafsly, Traffy, Flowly,
BotoHub, DarkBoost, SubGram. (Axionna работает только с показами, см. ads.py.)

Задание это словарь:
    {"sponsor": "tgrass", "id": "123", "text": "...", "url": "https://...",
     "extra": {...}}

Для каждого сервиса:
    fetch_<имя>(user, api_key) -> список заданий
    state_<имя>(user_id, api_key, task) -> "yes" | "no" | "unk"
        yes: выполнено/подписан, no: явно отписан или не выполнено,
        unk: сервис не сказал определённо
"""
import time

import aiohttp

from database import get_sponsor, get_sponsors, get_user, is_task_done

# True, если бот подключён к PiarFlow без токена бота
PIARFLOW_NO_TOKEN = False

current = {}        # user_id -> текущее задание
skipped = {}        # user_id -> {полные id пропущенных заданий}
skipped_rids = {}   # user_id -> {id ресурсов пропущенных заданий (Traffy)}

# слежение за сервисами: ошибки и пустые ответы подряд
fails = {}
empties = {}
last_alert = {}
alert_cb = None
ALERT_EVERY = 6 * 3600   # не чаще раза в 6 часов на один сервис
FAILS_LIMIT = 5
EMPTY_LIMIT = 30

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


def set_alert(cb):
    global alert_cb
    alert_cb = cb


async def _alert(name, kind, text):
    now = time.time()
    if now - last_alert.get((name, kind), 0) < ALERT_EVERY:
        return
    last_alert[(name, kind)] = now
    if alert_cb:
        try:
            await alert_cb(text)
        except Exception:
            pass


def user_info(u):
    """Данные пользователя из aiogram User."""
    return {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name or "",
        "lang": u.language_code or "ru",
        "premium": bool(u.is_premium),
    }


def user_info_row(r):
    """Данные пользователя из строки базы."""
    return {
        "id": r["user_id"],
        "username": r["username"],
        "first_name": r["first_name"] or "",
        "lang": r["lang"] or "ru",
        "premium": bool(r["premium"]),
    }


async def _post(url, headers, payload, key_errors=(401, 403)):
    """key_errors: HTTP-коды, которые означают неверный ключ."""
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(url, json=payload, headers=headers) as r:
            if r.status in key_errors:
                raise RuntimeError(f"HTTP {r.status}: ключ не принят")
            return await r.json(content_type=None)


def _task(sponsor, tid, text, url, **extra):
    return {"sponsor": sponsor, "id": str(tid), "text": text,
            "url": url, "extra": extra}


def _excluded(user_id, sponsor):
    """Id пропущенных заданий этого сервиса (без префикса)."""
    pref = sponsor + ":"
    return [t[len(pref):] for t in skipped.get(user_id, ())
            if t.startswith(pref)]


# ---------- Tgrass ----------

async def _tgrass_offers(user, key):
    return await _post(
        "https://tgrass.space/tasks", {"Auth": key},
        {"tg_user_id": user["id"], "tg_login": user["username"],
         "lang": user["lang"], "is_premium": user["premium"]})


async def fetch_tgrass(user, key):
    data = await _tgrass_offers(user, key)
    if data.get("status") == "ok":
        # человек подписан на все текущие офферы: сбрасываем время
        # обновления и просим новые, не дожидаясь
        await _post("https://tgrass.space/reset_offers", {"Auth": key},
                    {"tg_user_id": user["id"]})
        data = await _tgrass_offers(user, key)
    out = []
    for o in data.get("offers") or []:
        if o.get("subscribed"):
            continue
        text = TYPE_TEXT.get(o.get("type"), DEFAULT_TEXT)
        out.append(_task("tgrass", o["offer_id"], text, o.get("link")))
    return out


async def state_tgrass(uid, key, task):
    data = await _post(
        "https://tgrass.space/check", {"Auth": key},
        {"tg_user_id": uid, "offer_id": int(task["id"])})
    st = data.get("status")
    if st == "subscribed" and not data.get("is_fake"):
        return "yes"
    if st in ("not_subscribed", "unsubscribed"):
        return "no"
    return "unk"


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
        f"{PF}/sponsors", {"Authorization": f"Bearer {key}"}, payload,
        key_errors=(401,))  # 403 = у этого человека заданий нет
    out = []
    for s in data.get("sponsors") or []:
        if s.get("status") == "subscribed":
            continue
        out.append(_task("piarflow", s["link"], DEFAULT_TEXT, s["link"]))
    return out


async def state_piarflow(uid, key, task):
    data = await _post(
        f"{PF}/sponsors/check", {"Authorization": f"Bearer {key}"},
        {"user_id": uid, "links": [task["url"] or task["id"]]},
        key_errors=(401,))
    items = data.get("sponsors") or []
    if items and all(i.get("status") == "subscribed" for i in items):
        return "yes"
    if any(i.get("status") == "unsubscribed" for i in items):
        return "no"
    return "unk"


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


async def state_flyer(uid, key, task):
    data = await _post(
        f"{FL}/check_task", {}, {"key": key, "signature": task["id"]})
    res = data.get("result")
    if res in ("complete", "waiting"):
        return "yes"
    if res == "abort":   # выполнял, но отписался
        return "no"
    return "unk"


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


async def state_trafsly(uid, key, task):
    data = await _post(
        f"{TS}/confirm-subscription", {"Auth": key},
        {"user_id": uid, "ads_id": task["extra"]["ads_id"]})
    return "yes" if data.get("subscribed") else "unk"


# ---------- Traffy ----------

TR = "https://api.traffy.ai/publisher"


async def fetch_traffy(user, key):
    payload = {"telegram_id": user["id"], "limit": 5,
               "first_name": user["first_name"],
               "username": user["username"],
               "language_code": user["lang"]}
    rids = list(skipped_rids.get(user["id"], ()))[:200]
    if rids:
        # пропущенные не выдаются снова, и Traffy даёт другие задания
        payload["exclude_resource_ids"] = rids
    data = await _post(
        f"{TR}/tasks", {"x-publisher-api-key": key}, payload,
        key_errors=(401,))
    out = []
    for t in data.get("tasks") or []:
        title = t.get("title")
        text = (f"Подпишись на «{title}» и нажми «Подтвердить»"
                if title else DEFAULT_TEXT)
        out.append(_task(
            "traffy", t["assignment_id"], text, t.get("target_link"),
            rid=t.get("target_resource_telegram_id")))
    return out


async def state_traffy(uid, key, task):
    data = await _post(
        f"{TR}/tasks/check", {"x-publisher-api-key": key},
        {"telegram_id": uid, "assignment_ids": [task["id"]]},
        key_errors=(401,))
    results = data.get("results") or []
    if not results:
        return "unk"
    r = results[0]
    # rewarded=False: вступил не по ссылке задания, награды нет
    if r.get("status") == "completed" and r.get("rewarded") is not False:
        return "yes"
    if r.get("reason") == "payout_cancelled":   # отписался в период удержания
        return "no"
    return "unk"


# ---------- Flowly ----------

FW = "https://flowly.guru/api/v1"


async def _flowly_offers(user, key):
    return await _post(
        f"{FW}/offers", {"Auth": key},
        {"tg_user_id": user["id"], "lang": user["lang"],
         "is_premium": bool(user["premium"]), "offers_limit": 3},
        key_errors=(401,))


async def fetch_flowly(user, key):
    data = await _flowly_offers(user, key)
    if data.get("status") == "ok":
        await _post(f"{FW}/reset_offers", {"Auth": key},
                    {"tg_user_id": user["id"]}, key_errors=(401,))
        data = await _flowly_offers(user, key)
    out = []
    for o in data.get("offers") or []:
        if o.get("subscribed"):
            continue
        text = TYPE_TEXT.get(o.get("type"), DEFAULT_TEXT)
        out.append(_task("flowly", o["offer_id"], text, o.get("link")))
    return out


async def state_flowly(uid, key, task):
    data = await _post(
        f"{FW}/check", {"Auth": key},
        {"tg_user_id": uid, "offer_id": int(task["id"])},
        key_errors=(401,))
    st = data.get("status")
    if st == "subscribed":
        return "yes"
    if st == "not_subscribed":
        return "no"
    return "unk"


# ---------- BotoHub (задания по одному) ----------

BH = "https://botohub.me/get-tasks"


async def _bh(key, uid, **extra):
    payload = {"chat_id": uid, "is_task": True}
    payload.update(extra)
    return await _post(BH, {"Auth": key}, payload, key_errors=(401,))


async def fetch_botohub(user, key):
    data = await _bh(key, user["id"])
    if data.get("fake") or data.get("skip") or data.get("completed"):
        return []
    links = (data.get("tasks") or [])[:1]
    return [_task("botohub", link, DEFAULT_TEXT, link) for link in links]


async def state_botohub(uid, key, task):
    # повторный запрос: prev_success=true значит предыдущее выполнено
    data = await _bh(key, uid)
    return "yes" if data.get("prev_success") else "unk"


async def hook_botohub(uid, key, task):
    await _bh(key, uid, skip=True)


# ---------- DarkBoost (задания по одному) ----------

DB = "https://darkboosts.com/api/v1"


async def fetch_darkboost(user, key):
    payload = {"user_id": user["id"], "chat_id": user["id"],
               "is_premium": bool(user["premium"])}
    if user["username"]:
        payload["username"] = user["username"]
    if user["first_name"]:
        payload["first_name"] = user["first_name"]
    if user["lang"]:
        payload["language_code"] = user["lang"]
    data = await _post(f"{DB}/tasks/next", {"Auth": key}, payload)
    task = data.get("task")
    if data.get("status") != "ok" or not task:
        return []
    return [_task("darkboost", data["session_id"], DEFAULT_TEXT,
                  task.get("link"))]


async def state_darkboost(uid, key, task):
    data = await _post(
        f"{DB}/tasks/check", {"Auth": key},
        {"user_id": uid, "session_id": int(task["id"])})
    return "yes" if data.get("status") == "ok" else "unk"


async def hook_darkboost(uid, key, task):
    await _post(f"{DB}/tasks/skip", {"Auth": key},
                {"user_id": uid, "session_id": int(task["id"])})


# ---------- SubGram ----------

SG = "https://api.subgram.org/get-sponsors"


def _sg_payload(info):
    payload = {"user_id": info["id"], "chat_id": info["id"],
               "max_sponsors": 5, "get_links": 1,
               "is_premium": 1 if info["premium"] else 0,
               "first_name": info["first_name"],
               "language_code": info["lang"]}
    if info["username"]:
        payload["username"] = info["username"]
    return payload


def _sg_sponsors(data):
    return (data.get("additional") or {}).get("sponsors") or []


def _sg_id(s):
    return str(s.get("resource_id") or s.get("link"))


async def fetch_subgram(user, key):
    payload = _sg_payload(user)
    ex = _excluded(user["id"], "subgram")
    if ex:
        payload["exclude_resource_ids"] = ex[:500]
    data = await _post(SG, {"Auth": key}, payload)
    out = []
    for s in _sg_sponsors(data):
        if s.get("status") != "unsubscribed":
            continue
        if not s.get("available_now", True):
            continue
        text = TYPE_TEXT.get(s.get("type"), DEFAULT_TEXT)
        out.append(_task("subgram", _sg_id(s), text, s.get("link")))
    return out


async def state_subgram(uid, key, task):
    row = await get_user(uid)
    info = user_info_row(row) if row else {
        "id": uid, "username": None, "first_name": "", "lang": "ru",
        "premium": False}
    data = await _post(SG, {"Auth": key}, _sg_payload(info))
    for s in _sg_sponsors(data):
        if _sg_id(s) == task["id"]:
            # notgetted: подписан, но Telegram не засчитал, награды нет
            return {"subscribed": "yes",
                    "unsubscribed": "no"}.get(s.get("status"), "unk")
    return "yes" if data.get("status") == "ok" else "unk"


FETCHERS = {
    "tgrass": fetch_tgrass,
    "piarflow": fetch_piarflow,
    "flyer": fetch_flyer,
    "trafsly": fetch_trafsly,
    "traffy": fetch_traffy,
    "flowly": fetch_flowly,
    "botohub": fetch_botohub,
    "darkboost": fetch_darkboost,
    "subgram": fetch_subgram,
}

STATES = {
    "tgrass": state_tgrass,
    "piarflow": state_piarflow,
    "flyer": state_flyer,
    "trafsly": state_trafsly,
    "traffy": state_traffy,
    "flowly": state_flowly,
    "botohub": state_botohub,
    "darkboost": state_darkboost,
    "subgram": state_subgram,
}

# сервисы, у которых можно безопасно перепроверить старое задание
RECHECKABLE = {"tgrass", "piarflow", "flyer", "traffy", "flowly", "subgram"}

# что делать у сервиса при нажатии «Пропустить»
SKIP_HOOKS = {"botohub": hook_botohub, "darkboost": hook_darkboost}


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
            n = fails[s["name"]] = fails.get(s["name"], 0) + 1
            if n >= FAILS_LIMIT:
                if "ключ не принят" in str(e):
                    msg = (f"⚠️ {s['name']}: ключ не принят ({e}). "
                           "Проверь ключ в «Спонсоры» и в кабинете "
                           "сервиса.")
                else:
                    msg = (f"⚠️ {s['name']}: сервис не отвечает или "
                           f"отвечает с ошибкой ({n} раз подряд).\n"
                           f"Последняя ошибка: {e}")
                await _alert(s["name"], "err", msg)
            continue
        fails[s["name"]] = 0
        if tasks:
            empties[s["name"]] = 0
        else:
            n = empties[s["name"]] = empties.get(s["name"], 0) + 1
            if n >= EMPTY_LIMIT:
                await _alert(
                    s["name"], "empty",
                    f"⚠️ {s['name']}: {n} запросов подряд без заданий.\n"
                    "Это не всегда поломка: люди могли выполнить всё, "
                    "у сервиса может быть время обновления или "
                    "ограничения по языку и стране. Если так всё время, "
                    "проверь настройки бота в кабинете сервиса.")
        for task in tasks or []:
            tid = full_id(task)
            if tid in exclude or await is_task_done(uid, tid):
                continue
            current[uid] = task
            return task
    exclude.clear()  # пропущенные снова станут доступны
    skipped_rids.pop(uid, None)
    current.pop(uid, None)
    return None


async def _state(user_id, task):
    s = await get_sponsor(task["sponsor"])
    fn = STATES.get(task["sponsor"])
    if not s or not fn or not s["api_key"]:
        return "unk"
    return await fn(user_id, s["api_key"], task)


async def check_task(user_id, task):
    """True, если пользователь выполнил задание."""
    try:
        return await _state(user_id, task) == "yes"
    except Exception as e:
        print(f"[{task['sponsor']}] check error: {e}")
        return False


async def recheck(user_id, task_id, url):
    """Перепроверка старого задания: True подписан, False отписался,
    None неизвестно (или сервис не умеет)."""
    sponsor, _, tid = task_id.partition(":")
    if sponsor not in RECHECKABLE:
        return None
    task = {"sponsor": sponsor, "id": tid, "url": url,
            "extra": {"ads_id": tid}}
    state = await _state(user_id, task)
    return {"yes": True, "no": False}.get(state)


async def skip_task(user_id):
    task = current.pop(user_id, None)
    if not task:
        return
    skipped.setdefault(user_id, set()).add(full_id(task))
    rid = (task.get("extra") or {}).get("rid")
    if rid:
        skipped_rids.setdefault(user_id, set()).add(str(rid))
    hook = SKIP_HOOKS.get(task["sponsor"])
    if hook:
        s = await get_sponsor(task["sponsor"])
        if s and s["api_key"]:
            try:
                await hook(user_id, s["api_key"], task)
            except Exception as e:
                print(f"[{task['sponsor']}] skip error: {e}")
