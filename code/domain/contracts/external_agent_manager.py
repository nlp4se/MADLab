from abc import ABC

from .agent_record import AgentDefinition


class ExternalAgentManager(ABC):
    """Defaults correspond to a stateless provider, where the agent only exists as its
    local AgentDefinition. Providers override these methods to validate the agent or,
    if stateful, to create, update and delete it on their side."""

    def create_agent(self, agent: AgentDefinition) -> None:
        pass

    def get_model(self, agent: AgentDefinition) -> str:
        return agent.model

    def change_model(self, agent: AgentDefinition, new_model: str) -> None:
        pass

    def delete_agent(self, agent: AgentDefinition) -> None:
        pass
