from abc import ABC, abstractmethod
from typing import Callable


class EventBus(ABC):
    @abstractmethod
    def subscribe(self, channel: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def send(self, channel: str, **kwargs) -> None:
        pass

    @abstractmethod
    def unsubscribe(self, channel: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def unsubscribe_agent(self, callback: Callable) -> None:
        pass

    @abstractmethod
    def unsubscribe_all(self) -> None:
        pass
