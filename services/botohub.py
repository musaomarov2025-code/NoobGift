import logging
import aiohttp

from .base import BaseService, Task

log = logging.getLogger("services.botohub")


class BotohubService(BaseService):
    name = "botohub"
    BASE = "https://botohub.me/api"
    TIMEOUT = aiohttp.ClientTimeout(total=15)
    HEADERS = {"User-Agent": "StarsBot/1.0", "Accept": "application/json"}

    async def get_tasks(self, user_id: int) -> list[Task]:
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=self.HEADERS) as s:
                async with s.post(f"{self.BASE}/get-tasks", json={
                    "token": self.api_key,
                    "user_id": user_id,
                }) as r:
                    if r.status != 200:
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"get_tasks error: {e}")
            return []

        tasks: list[Task] = []
        for t in data.get("tasks", data.get("response", [])):
            if t.get("fake"):
                continue
            if t.get("completed"):
                continue
            tasks.append(Task(
                task_id=str(t.get("id") or t.get("chat_id") or ""),
                url=t.get("link") or t.get("url", ""),
                title=t.get("title", "Канал"),
                service=self.name,
            ))
        return tasks

    async def check(self, user_id: int, task_id: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=self.HEADERS) as s:
                async with s.post(f"{self.BASE}/get-tasks", json={
                    "token": self.api_key,
                    "user_id": user_id,
                }) as r:
                    data = await r.json()
        except Exception as e:
            log.warning(f"check error: {e}")
            return False

        for t in data.get("tasks", []):
            if str(t.get("id") or t.get("chat_id")) == str(task_id):
                return bool(t.get("completed"))
        return False
