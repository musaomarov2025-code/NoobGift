import logging
import aiohttp

from .base import BaseService, Task

log = logging.getLogger("services.tgrass")


class TgrassService(BaseService):
    name = "tgrass"
    BASE = "https://tgrass.space/api"
    TIMEOUT = aiohttp.ClientTimeout(total=15)
    HEADERS = {"User-Agent": "StarsBot/1.0", "Accept": "application/json"}

    async def get_tasks(self, user_id: int) -> list[Task]:
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=self.HEADERS) as s:
                async with s.post(f"{self.BASE}/offers", json={
                    "api_key": self.api_key,
                    "user_id": user_id,
                }) as r:
                    if r.status != 200:
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"get_tasks error: {e}")
            return []

        if data.get("status") != "ok":
            return []

        return [
            Task(
                task_id=str(t.get("id")),
                url=t.get("link", ""),
                title=t.get("title", "Канал"),
                service=self.name,
            )
            for t in data.get("offers", [])
        ]

    async def check(self, user_id: int, task_id: str) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=self.HEADERS) as s:
                async with s.post(f"{self.BASE}/check", json={
                    "api_key": self.api_key,
                    "user_id": user_id,
                    "offer_id": task_id,
                }) as r:
                    data = await r.json()
        except Exception as e:
            log.warning(f"check error: {e}")
            return False
        return data.get("status") == "ok"
