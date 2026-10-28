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
    
    tasks = []
    for s in services:
        try:
            # ЖЕСТКИЙ ТАЙМАУТ 5 СЕКУНД НА КАЖДЫЙ СЕРВИС
            res = await asyncio.wait_for(s.get_tasks(user), timeout=5.0)
            if isinstance(res, list): 
                tasks.extend(res)
        except asyncio.TimeoutError:
            log.warning(f"{s.name} get_tasks TIMEOUT (не ответил за 5 сек)")
        except Exception as e:
            log.warning(f"{s.name} get_tasks failed: {e}")
            
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
            try:
                # Таймаут на проверку тоже 5 секунд
                return await asyncio.wait_for(s.check(user, task.task_id), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning(f"{s.name} check TIMEOUT")
                return False
            except Exception as e:
                log.warning(f"{s.name} check failed: {e}")
                return False
    return False
