import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.tgrass")

class TgrassService(BaseService):
    name = "tgrass"
    URL = "https://tgrass.space/offers"
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {
            "tg_user_id": user["user_id"],
            "is_premium": False, # При необходимости можно определять через Telegram API
            "lang": "ru",
            "tg_login": user.get("username"),
        }
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.URL, json=payload) as r:
                    if r.status != 200: 
                        log.error(f"Tgrass API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"tgrass get_tasks: {e}")
            return []

        if data.get("status") == "no_offers" or not data.get("offers"):
            return []

        return [
            Task(task_id=str(t.get("offer_id")), url=t.get("link"), title=t.get("name") or "Канал", service=self.name)
            for t in data["offers"] if not t.get("subscribed")
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        tasks = await self.get_tasks(user)
        return any(t.task_id == str(task_id) for t in tasks)
