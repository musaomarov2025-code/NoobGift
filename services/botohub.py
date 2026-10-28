import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.botohub")

class BotohubService(BaseService):
    name = "botohub"
    URL = "https://botohub.me/get-tasks"
    TIMEOUT = aiohttp.ClientTimeout(total=15)

    async def get_tasks(self, user: dict) -> list[Task]:
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {"chat_id": user["user_id"], "is_task": True}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.URL, json=payload) as r:
                    if r.status not in (200, 201):
                        log.error(f"Botohub API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"botohub get_tasks: {e}")
            return []

        if data.get("skip") or data.get("completed") or data.get("fake"):
            return []

        return [
            Task(task_id=link, url=link, title="Канал", service=self.name)
            for link in data.get("tasks", [])
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        # В режиме is_task=true Botohub сам проверяет предыдущую задачу (prev_success)
        headers = {"Content-Type": "application/json", "Auth": self.api_key}
        payload = {"chat_id": user["user_id"], "is_task": True, "skip": False}
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.URL, json=payload) as r:
                    data = await r.json()
        except Exception:
            return False
        return bool(data.get("prev_success"))
