import logging
import aiohttp
from .base import BaseService, Task

log = logging.getLogger("services.tgrass")

class TgrassService(BaseService):
    name = "tgrass"
    # ТОЧНЫЙ URL ИЗ ДОКУМЕНТАЦИИ
    URL = "https://tgrass.space/offers"
    TIMEOUT = aiohttp.ClientTimeout(total=10)

    async def get_tasks(self, user: dict) -> list[Task]:
        # Ключ передается в заголовке Auth (без Bearer)
        headers = {
            "Content-Type": "application/json", 
            "Auth": self.api_key
        }
        # Обязательные поля по документации
        payload = {
            "tg_user_id": user["user_id"],
            "is_premium": False,
            "lang": "ru",
            "tg_login": user.get("username") or "",
        }
        
        try:
            async with aiohttp.ClientSession(timeout=self.TIMEOUT, headers=headers) as s:
                async with s.post(self.URL, json=payload) as r:
                    if r.status not in (200, 201):
                        log.error(f"Tgrass API Error {r.status}: {await r.text()}")
                        return []
                    data = await r.json()
        except Exception as e:
            log.warning(f"tgrass get_tasks: {e}")
            return []

        # Если статус не ok или офферов нет — возвращаем пустой список
        if data.get("status") != "ok" or not data.get("offers"):
            return []

        # Собираем только те офферы, на которые юзер еще не подписан
        return [
            Task(
                task_id=str(t.get("offer_id")),
                url=t.get("link"),
                title=t.get("name") or "Канал",
                service=self.name
            )
            for t in data["offers"] if not t.get("subscribed")
        ]

    async def check(self, user: dict, task_id: str) -> bool:
        # По документации проверка — это повторный запрос к /offers.
        # Если оффер с таким ID исчез из списка (или status стал ok) — значит, подписался.
        tasks = await self.get_tasks(user)
        return not any(t.task_id == str(task_id) for t in tasks)
