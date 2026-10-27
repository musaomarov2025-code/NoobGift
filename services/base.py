from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass(slots=True)
class Task:
    """Универсальное задание (приводится к единому виду из любого сервиса)."""
    task_id: str
    url: str
    title: str
    service: str

    def key(self) -> str:
        return f"{self.service}:{self.task_id}"


class BaseService(ABC):
    """Базовый интерфейс для всех сервисов заданий."""
    name: str = ""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    async def get_tasks(self, user_id: int) -> list[Task]:
        """Вернуть список доступных заданий для юзера (не подписанных)."""
        ...

    @abstractmethod
    async def check(self, user_id: int, task_id: str) -> bool:
        """Проверить, выполнено ли задание (подписан ли юзер)."""
        ...
