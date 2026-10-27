import json
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

import config

_lock = asyncio.Lock()

DEFAULT = {
    "users": {},
    "withdrawals": [],
    "promocodes": {},
    "ads": {},
    "greeting": {
        "text": "👋 Добро пожаловать!\n\n⭐️ Зарабатывай Telegram Stars, выполняя задания.",
        "media": None,
        "buttons": [],
    },
    "settings": {
        "ref_percent": 10,
        "task_reward": 0.4,
        "withdraw_channel": "",
        "withdraw_counter": 0,
        "services_enabled": {
            "botohub": True, "tgrass": True, "traffy": True,
            "trafsly": True, "piarflow": True,
        },
        "service_keys": {
            "botohub": "", "tgrass": "", "traffy": "",
            "trafsly": "", "piarflow": "",
        },
    },
    "stats": {
        "total_users": 0, "new_today": 0, "new_today_date": "",
        "tasks_done_total": 0, "tasks_done_today": 0, "tasks_done_yesterday": 0,
        "refs_total": 0, "withdrawn_total": 0.0, "hold_total": 0.0,
        "unsubscribed_total": 0,
    },
}

_data: Optional[dict] = None

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.isoformat()

def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)

def _load():
    global _data
    if _data is not None:
        return
    if os.path.exists(config.DB_PATH):
        try:
            with open(config.DB_PATH, "r", encoding="utf-8") as f:
                _data = json.load(f)
        except Exception:
            _data = json.loads(json.dumps(DEFAULT))
    else:
        _data = json.loads(json.dumps(DEFAULT))

    for k, v in DEFAULT.items():
        if k not in _data:
            _data[k] = v
    for k, v in DEFAULT["settings"].items():
        if k not in _data["settings"]:
            _data["settings"][k] = v
    for k, v in DEFAULT["stats"].items():
        if k not in _data["stats"]:
            _data["stats"][k] = v

def _save():
    tmp = config.DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.DB_PATH)

async def init():
    async with _lock:
        _load()
        today = _now().strftime("%Y-%m-%d")
        if _data["stats"].get("new_today_date") != today:
            _data["stats"]["tasks_done_yesterday"] = _data["stats"].get("tasks_done_today", 0)
            _data["stats"]["tasks_done_today"] = 0
            _data["stats"]["new_today"] = 0
            _data["stats"]["new_today_date"] = today
            _save()

async def get_user(user_id: int) -> Optional[dict]:
    async with _lock:
        _load()
        return _data["users"].get(str(user_id))

async def create_user(user_id: int, username: Optional[str], first_name: str, referrer_id: Optional[int] = None, ad_code: Optional[str] = None) -> dict:
    async with _lock:
        _load()
        uid = str(user_id)
        if uid in _data["users"]:
            return _data["users"][uid]

        if referrer_id and str(referrer_id) == uid:
            referrer_id = None

        user = {
            "user_id": user_id, "username": username, "first_name": first_name or "",
            "balance": 0.0, "hold": 0.0, "total_withdrawn": 0.0,
            "referrer_id": referrer_id, "refs_count": 0, "refs_earned": 0.0,
            "tasks_done": 0, "reg_date": _iso(_now()), "is_banned": False,
            "is_fake_botohub": False, "skipped_tasks": [], "hold_items": [],
            "ad_code": ad_code,
        }
        _data["users"][uid] = user
        st = _data["stats"]
        st["total_users"] = len(_data["users"])
        st["new_today"] += 1

        if referrer_id:
            ref = _data["users"].get(str(referrer_id))
            if ref:
                ref["refs_count"] += 1
                st["refs_total"] += 1
        _save()
        return user

async def update_user(user_id: int, **fields):
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if u:
            for k, v in fields.items():
                u[k] = v
            _save()

async def add_balance(user_id: int, amount: float):
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if u:
            u["balance"] = round(u["balance"] + amount, 4)
            _save()

async def add_hold(user_id: int, amount: float, kind: str = "task", from_user: Optional[int] = None, task_id: Optional[str] = None, hours: int = 24):
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if not u: return
        unlock = _now() + timedelta(hours=hours)
        u["hold"] = round(u["hold"] + amount, 4)
        u["hold_items"].append({
            "amount": round(amount, 4), "kind": kind, "from_user": from_user,
            "task_id": task_id, "created_at": _iso(_now()), "unlock_at": _iso(unlock),
        })
        _data["stats"]["hold_total"] = round(_data["stats"].get("hold_total", 0) + amount, 4)
        _save()

async def process_holds() -> list[tuple[int, float, str]]:
    released = []
    async with _lock:
        _load()
        now = _now()
        for uid, u in _data["users"].items():
            remaining = []
            for item in u.get("hold_items", []):
                try:
                    unlock = _parse(item["unlock_at"])
                except Exception:
                    continue
                if unlock <= now:
                    amount = float(item["amount"])
                    u["balance"] = round(u["balance"] + amount, 4)
                    u["hold"] = round(max(0, u["hold"] - amount), 4)
                    released.append((int(uid), amount, item.get("kind", "task")))
                else:
                    remaining.append(item)
            if len(remaining) != len(u.get("hold_items", [])):
                u["hold_items"] = remaining
        if released:
            _save()
    return released

async def increment_tasks_done(user_id: int):
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if u:
            u["tasks_done"] += 1
            # Если юзер пришел с рекламы, засчитываем ей выполнение
            if u.get("ad_code") and u["ad_code"] in _data["ads"]:
                _data["ads"][u["ad_code"]]["tasks_done"] += 1
        _data["stats"]["tasks_done_total"] += 1
        _data["stats"]["tasks_done_today"] += 1
        _save()

async def add_ref_earned(user_id: int, amount: float):
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if u:
            u["refs_earned"] = round(u["refs_earned"] + amount, 4)
            _save()

async def get_setting(key: str, default=None):
    async with _lock:
        _load()
        return _data["settings"].get(key, default)

async def set_setting(key: str, value: Any):
    async with _lock:
        _load()
        _data["settings"][key] = value
        _save()

async def get_service_enabled(name: str) -> bool:
    async with _lock:
        _load()
        return bool(_data["settings"]["services_enabled"].get(name, False))

async def set_service_enabled(name: str, enabled: bool):
    async with _lock:
        _load()
        _data["settings"]["services_enabled"][name] = enabled
        _save()

async def get_service_key(name: str) -> str:
    async with _lock:
        _load()
        return _data["settings"]["service_keys"].get(name, "")

async def set_service_key(name: str, key: str):
    async with _lock:
        _load()
        _data["settings"]["service_keys"][name] = key
        _save()

async def get_stats() -> dict:
    async with _lock:
        _load()
        return dict(_data["stats"])

async def get_top_users(limit: int = 5) -> list[dict]:
    async with _lock:
        _load()
        users = sorted(_data["users"].values(), key=lambda u: (u.get("tasks_done", 0), u.get("balance", 0)), reverse=True)
        return [dict(u) for u in users[:limit]]

async def create_withdrawal(user_id: int, username: Optional[str], first_name: str, amount: float) -> dict:
    async with _lock:
        _load()
        u = _data["users"].get(str(user_id))
        if not u or u["balance"] < amount:
            return {"error": "not_enough"}
        u["balance"] = round(u["balance"] - amount, 4)
        _data["settings"]["withdraw_counter"] += 1
        wid = _data["settings"]["withdraw_counter"]
        w = {
            "id": wid, "user_id": user_id, "username": username, "first_name": first_name,
            "amount": round(amount, 4), "status": "pending", "created_at": _iso(_now()), "channel_msg_id": None,
        }
        _data["withdrawals"].append(w)
        _save()
        return w

async def get_withdrawal(wid: int) -> Optional[dict]:
    async with _lock:
        _load()
        for w in _data["withdrawals"]:
            if w["id"] == wid: return dict(w)
        return None

async def list_withdrawals(status: Optional[str] = None) -> list[dict]:
    async with _lock:
        _load()
        items = _data["withdrawals"]
        if status: items = [w for w in items if w["status"] == status]
        return [dict(w) for w in items]

async def update_withdrawal(wid: int, status: str):
    async with _lock:
        _load()
        for w in _data["withdrawals"]:
            if w["id"] == wid:
                w["status"] = status
                if status == "accepted":
                    u = _data["users"].get(str(w["user_id"]))
                    if u:
                        u["total_withdrawn"] = round(u["total_withdrawn"] + w["amount"], 4)
                        _data["stats"]["withdrawn_total"] = round(_data["stats"].get("withdrawn_total", 0) + w["amount"], 4)
                elif status == "rejected":
                    u = _data["users"].get(str(w["user_id"]))
                    if u: u["balance"] = round(u["balance"] + w["amount"], 4)
                _save()
                return True
        return False

async def set_withdrawal_msg(wid: int, msg_id: int):
    async with _lock:
        _load()
        for w in _data["withdrawals"]:
            if w["id"] == wid:
                w["channel_msg_id"] = msg_id
                _save()
                return

async def create_promocode(code: str, amount: float, limit: int) -> dict:
    async with _lock:
        _load()
        if code in _data["promocodes"]:
            return {"error": "exists"}
        _data["promocodes"][code] = {"code": code, "amount": round(amount, 4), "limit": limit, "used": 0, "users": []}
        _save()
        return _data["promocodes"][code]

async def use_promocode(code: str, user_id: int) -> dict:
    async with _lock:
        _load()
        p = _data["promocodes"].get(code)
        if not p: return {"error": "not_found"}
        if user_id in p["users"]: return {"error": "already_used"}
        if p["used"] >= p["limit"]: return {"error": "limit_reached"}
        p["used"] += 1
        p["users"].append(user_id)
        u = _data["users"].get(str(user_id))
        if u: u["balance"] = round(u["balance"] + p["amount"], 4)
        _save()
        return {"amount": p["amount"]}

async def get_promocodes() -> list[dict]:
    async with _lock:
        _load()
        return list(_data["promocodes"].values())

async def create_ad(owner_id: int, name: str, price: float) -> dict:
    async with _lock:
        _load()
        code = f"ad{len(_data['ads']) + 1}"
        while code in _data["ads"]: code += "_"
        _data["ads"][code] = {"code": code, "owner_id": owner_id, "name": name, "price": round(price, 4), "clicks": 0, "tasks_done": 0, "created_at": _iso(_now())}
        _save()
        return _data["ads"][code]

async def get_ad(code: str) -> Optional[dict]:
    async with _lock:
        _load()
        return _data["ads"].get(code)

async def incr_ad_stat(code: str, field: str):
    async with _lock:
        _load()
        ad = _data["ads"].get(code)
        if ad and field in ad:
            ad[field] += 1
            _save()

async def list_ads() -> list[dict]:
    async with _lock:
        _load()
        return list(_data["ads"].values())

async def get_greeting() -> dict:
    async with _lock:
        _load()
        return dict(_data["greeting"])

async def set_greeting(**kwargs):
    async with _lock:
        _load()
        for k, v in kwargs.items():
            _data["greeting"][k] = v
        _save()

async def export_data() -> dict:
    async with _lock:
        _load()
        return json.loads(json.dumps(_data))

async def import_data(new_data: dict):
    global _data
    async with _lock:
        _data = new_data
        _load()
        _save()
