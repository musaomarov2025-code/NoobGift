import aiohttp
from config import TGRASS_URL
from database import get_setting


def tgrass_enabled():
    return get_setting("tgrass_enabled") == "1"


def tgrass_key():
    return get_setting("tgrass_api_key") or ""


def _base_payload(user_id, username=None, lang=None, is_premium=False, limit=None):
    payload = {
        "tg_user_id": int(user_id),
        "is_premium": bool(is_premium),
        "lang": lang or "ru",
    }
    if username:
        payload["tg_login"] = username
    if limit:
        payload["offers_limit"] = int(limit)
    return payload


async def _tgrass_request(path, payload):
    key = tgrass_key()
    if not key:
        return {"status": "error", "message": "no key", "offers": []}
    headers = {
        "Content-Type": "application/json",
        "Auth": key,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{TGRASS_URL}{path}",
                json=payload,
                headers=headers,
                ssl=False,  # у tgrass самоподписанный сертификат (см. их пример с verify=False)
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json(content_type=None)
                print(f"TGRASS {path}:", data)
                return data
    except Exception as e:
        print("Tgrass error:", e)
        return {"status": "error", "message": str(e), "offers": []}


async def get_offers(user_id, username=None, lang=None, is_premium=False, limit=6):
    return await _tgrass_request(
        "/offers",
        _base_payload(user_id, username, lang, is_premium, limit))


async def get_tasks(user_id, username=None, lang=None, is_premium=False, limit=10):
    return await _tgrass_request(
        "/tasks",
        _base_payload(user_id, username, lang, is_premium, limit))


async def check_offer(user_id, offer_id):
    return await _tgrass_request("/check", {
        "tg_user_id": int(user_id),
        "offer_id": int(offer_id),
    })
