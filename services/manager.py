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

SERVICE_NAMES = {"botohub": "Botohub", "tgrass": "Tgrass", "traffy": "Traffy", "trafsly": "Trafsly", "piarflow": "PiarFlow"}
_SERVICE_CLASSES = {"botohub": BotohubService, "tgrass": TgrassService, "traffy": TraffyService, "trafsly": TrafslyService, "piarflow": PiarFlowService}

async def _get_active_services() -> list[BaseService]:
    services = []
    for name, cls in _SERVICE_CLASSES.items():
        if not await database.get_service_enabled(name): continue
        key = await database.get_service_key(name)
        if not key: continue
        services.append(cls(key))
    return services

async def get_all_tasks(user: dict) -> list[Task]:
    services = await _get_active_services()
    if not services: return []
    results = await asyncio.gather(*(s.get_tasks(user) for s in services), return_exceptions=True)
    tasks = []
    for s, res in zip(services, results):
        if isinstance(res, list): tasks.extend(res)
        else: log.warning(f"{s.name} get_tasks failed: {res}")
    seen, unique = set(), []
    for t in tasks:
        if t.key() not in seen:
            seen.add(t.key())
            unique.append(t)
    return unique

async def check_task_in_services(user: dict, task: Task) -> bool:
    services = await _get_active_services()
    for s in services:
        if s.name == task.service:
            return await s.check(user, task.task_id)
    return False
