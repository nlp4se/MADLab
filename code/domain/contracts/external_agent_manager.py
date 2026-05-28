from abc import ABC, abstractmethod


class ExternalAgentManager(ABC):
    @abstractmethod
    def create_assistant(self, name: str, instructions: str, model: str, **kwargs) -> str:
        pass

    @abstractmethod
    def get_model(self, assistant_id: str) -> str:
        pass

    @abstractmethod
    def change_model(self, assistant_id: str, new_model: str) -> None:
        pass

    @abstractmethod
    def delete_assistant(self, assistant_id: str) -> None:
        pass

    @abstractmethod
    def list_assistants(self) -> dict[str, set[str]]:
        pass
