from abc import ABC, abstractmethod


class ExternalAgentManager(ABC):
    @abstractmethod
    def create_agent(self, name: str, instructions: str, model: str, **kwargs) -> str:
        pass

    @abstractmethod
    def get_model(self, agent_id: str) -> str:
        pass

    @abstractmethod
    def change_model(self, agent_id: str, new_model: str) -> None:
        pass

    @abstractmethod
    def delete_agent(self, agent_id: str) -> None:
        pass

    @abstractmethod
    def list_agents(self) -> dict[str, set[str]]:
        pass
