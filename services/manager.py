import asyncio
import logging

import database
from .base import Task, BaseService
from .botohub import BotohubService
from .tgrass import TgrassService
from .traffy import TraffyService
from .trafsly import TrafslyService
from .piarflow import PiarFlowService

log = logging.getLogger("services.manager")


SERVICE_NAMES = {
    "botohub": "Botohub",
    "tgrass": "Tgrass",
    "traffy": "Traffy",
    "trafsly": "Trafsly",
    "piarflow": "PiarFlow",
}

_SERVICE_CLASSES: dict[str, type[BaseService]] = {
    "botohub": BotohubService,
    "tgrass": TgrassService,
    "traffy": TraffyService,
    "trafsly": TrafslyService,
    "piarflow": PiarFlowService,
}


async def _get_active_services() -> list[BaseService]:
    """Собирает список активных сервисов (включённых в админке + с ключом)."""
    services: list[BaseService] = []
    for name, cls in _SERVICE_CLASSES.items():
        if not await database.get_service_enabled(name):
            continue
        key = await database.get_service_key(name)
        if not key:
            continue
        services.append(cls(key))
    return services


async def get_all_tasks(user_id: int) -> list[Task]:
    """Параллельно собирает задания со всех включённых сервисов."""
    services = await _get_active_services()
    if not services:
        return []

    results = await asyncio.gather(
        *(s.get_tasks(user_id) for s in services),
        return_exceptions=True,
    )

    tasks: list[Task] = []
    for s, res in zip(services, results):
        if isinstance(res, list):
            tasks.extend(res)
        else:
            log.warning(f"{s.name} get_tasks failed: {res}")

    # дедупликация по (service, task_id)
    seen = set()
    unique: list[Task] = []
    for t in tasks:
        if t.key() in seen:
            continue
        seen.add(t.key())
        unique.append(t)
    return unique


async def check_task_in_services(user_id: int, task: Task) -> bool:
    """Проверяет задание в сервисе, которому оно принадлежит."""
    services = await _get_active_services()
    for s in services:
        if s.name == task.service:
            return await s.check(user_id, task.task_id)
    return False
