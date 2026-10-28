import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.piarflow")

class PiarFlowService(BaseService):
    name = "piarflow"
    BASE = "https://piarflow.com/v1"
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {
            "user_id": user["user_id"],
            "chat_id": user["user_id"],
            "first_name": user.get("first_name") or "",
            "username": user.get("username") or "",
            "language_code": "ru",
            "max_sponsors": 5,
        }
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(f"{self.BASE}/sponsors", json=payload) as r:
                    if r.status not in (200, 201):
                        log.error(f"PiarFlow API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"piarflow get_tasks: {e}")
            return []

        return [
            Task(
                task_id=t.get("link"), 
                url=t.get("link"), 
                title="Канал", 
                service=self.name
            )
            for t in data.get("sponsors", []) if t.get("status") == "unsubscribed"
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {"user_id": user["user_id"], "links": [task_id]}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(f"{self.BASE}/sponsors/check", json=payload) as r:
                    if r.status not in (200, 201):
                        return False
                    data = await r.json()
        except Exception as e:
            log.warning(f"piarflow check: {e}")
            return False
        for sp in data.get("sponsors", []):
            if sp.get("link") == task_id and sp.get("status") == "subscribed":
                return True
        return False
