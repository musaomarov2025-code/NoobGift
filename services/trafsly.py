import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.trafsly")

class TrafslyService(BaseService):
    name = "trafsly"
    BASE = "https://trafsly.com/api" # Убрали api. и добавили /api
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {"user_id": user["user_id"]}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(f"{self.BASE}/get-sponsors", json=payload) as r:
                    if r.status not in (200, 201):
                        log.error(f"Trafsly API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"trafsly get_tasks: {e}")
            return []

        return [
            Task(task_id=str(t.get("id")), url=t.get("link"), title=t.get("title") or "Канал", service=self.name)
            for t in data.get("sponsors", []) if not t.get("subscribed")
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {"user_id": user["user_id"], "sponsor_id": task_id}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(f"{self.BASE}/confirm-subscription", json=payload) as r:
                    if r.status not in (200, 201):
                        return False
                    data = await r.json()
        except Exception as e:
            log.warning(f"trafsly check: {e}")
            return False
        return bool(data.get("success") or data.get("subscribed"))
