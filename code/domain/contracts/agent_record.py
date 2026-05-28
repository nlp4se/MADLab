from abc import ABC, abstractmethod


class AgentRecord(ABC):
    @abstractmethod
    def get_id(self, name: str) -> str:
        pass

    @abstractmethod
    def create(self, name: str, id: str) -> None:
        pass

    @abstractmethod
    def delete(self, name: str) -> bool:
        pass

    @abstractmethod
    def list_names(self) -> list[str]:
        pass
