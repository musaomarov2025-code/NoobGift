import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.traffy")

class TraffyService(BaseService):
    name = "traffy"
    URL = "https://api.traffy.ai/publisher/tasks"
    CHECK_URL = "https://api.traffy.ai/publisher/tasks/check"
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "x-publisher-api-key": self.api_key}
        payload = {
            "telegram_id": user["user_id"],
            "first_name": user.get("first_name"),
            "username": user.get("username"),
            "language_code": "ru",
        }
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.URL, json=payload) as r:
                    if r.status != 200: 
                        log.error(f"Traffy API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"traffy get_tasks: {e}")
            return []
            Task(task_id=str(t.get("assignment_id")), url=t.get("target_link"), title=t.get("title") or "Канал", service=self.name)
            for t in data.get("tasks", [])
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        headers = {"Content-Type": "application/json", "x-publisher-api-key": self.api_key}
        payload = {"telegram_id": user["user_id"], "assignment_id": task_id}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.CHECK_URL, json=payload) as r:
                    data = await r.json()
        except Exception as e:
            log.warning(f"traffy check: {e}")
            return False
        return bool(data.get("success") or data.get("completed"))
