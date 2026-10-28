import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.tgrass")

class TgrassService(BaseService):
    name = "tgrass"
    URL = "https://tgrass.space/api/v1/offers"
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {"tg_user_id": user["user_id"], "is_premium": False, "lang": "ru", "tg_login": user.get("username") or ""}
        
        async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
            async with s.post(self.URL, json=payload) as r:
                if r.status not in (200, 201):
                    raise Exception(f"HTTP {r.status}: {await r.text()}") # ВЫКИДЫВАЕМ ОШИБКУ
                data = await r.json()

        if data.get("status") != "ok" or not data.get("offers"):
            return []

        return [Task(task_id=str(t.get("offer_id")), url=t.get("link"), title=t.get("name") or "Канал", service=self.name) for t in data["offers"] if not t.get("subscribed")]

    async def check(self, user: dict, task_id: str) -> bool:
        tasks = await self.get_tasks(user)
        return not any(t.task_id == str(task_id) for t in tasks)
