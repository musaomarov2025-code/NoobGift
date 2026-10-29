import aiohttp
from config import TRAFFY_URL
from database import get_setting


def traffy_enabled():
    return get_setting("traffy_enabled") == "1"


def traffy_key():
    return get_setting("traffy_api_key") or ""


def _headers():
    key = traffy_key()
    return {
        "Content-Type": "application/json",
        "x-publisher-api-key": key,
    }


async def _traffy_request(method, path, payload=None, params=None):
    if not traffy_key():
        return {"ok": False, "error": "no key"}
    url = f"{TRAFFY_URL}{path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.request(
                method, url,
                json=payload if payload is not None else None,
                params=params,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                print(f"TRAFFY {path}:", data)
                return data
    except Exception as e:
        print("Traffy error:", e)
        return {"ok": False, "error": str(e)}


async def get_tasks(user_id, limit=6, username=None, first_name=None,
                    lang=None):
    payload = {"telegram_id": int(user_id), "limit": int(limit)}
    if username:
        payload["username"] = username
    if first_name:
        payload["first_name"] = first_name
    if lang:
        payload["language_code"] = lang
    return await _traffy_request("POST", "/tasks", payload)


async def check_tasks(user_id, assignment_ids):
    return await _traffy_request("POST", "/tasks/check", {
        "telegram_id": int(user_id),
        "assignment_ids": list(assignment_ids),
    })


async def me():
    return await _traffy_request("GET", "/me")
