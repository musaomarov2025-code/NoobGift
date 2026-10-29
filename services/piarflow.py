import aiohttp
from config import PIARFLOW_URL
from database import get_setting


def piarflow_enabled():
    return get_setting("piarflow_enabled") == "1"


def piarflow_key():
    return get_setting("piarflow_key") or ""


async def _piarflow_request(path, payload):
    key = piarflow_key()
    if not key:
        return {"status": "error", "message": "no key"}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{PIARFLOW_URL}{path}",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                print(f"PIARFLOW {path}:", data)
                return data
    except Exception as e:
        print("PiarFlow error:", e)
        return {"status": "error", "message": str(e)}


async def get_sponsors(user_id, chat_id, max_sponsors=1):
    return await _piarflow_request("/sponsors", {
        "user_id": user_id,
        "chat_id": chat_id,
        "max_sponsors": max_sponsors,
    })


async def check(user_id, links):
    return await _piarflow_request("/sponsors/check", {
        "user_id": user_id,
        "links": links,
    })
