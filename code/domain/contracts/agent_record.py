from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    model: str
    instructions: str
    temperature: float = 0.0
    schema_file_path: str | None = None


class AgentRecord(ABC):
    @abstractmethod
    def get(self, name: str) -> AgentDefinition:
        pass

    @abstractmethod
    def save(self, agent: AgentDefinition) -> None:
        pass

    @abstractmethod
    def delete(self, name: str) -> bool:
        pass

    @abstractmethod
    def list_names(self) -> list[str]:
        pass
