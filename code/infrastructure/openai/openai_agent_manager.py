from openai import OpenAI, NotFoundError

from ...domain.contracts.external_agent_manager import ExternalAgentManager
from ...domain.contracts.agent_record import AgentDefinition


class OpenAIAgentManager(ExternalAgentManager):
    MIN_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 2.0

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

    def _validate_model(self, model: str) -> None:
        try:
            self.client.models.retrieve(model)
        except NotFoundError:
            raise ValueError(
                f"OpenAI model '{model}' does not exist or is not accessible with the configured API key."
            )

    def _validate_temperature(self, temperature: float) -> None:
        if not self.MIN_TEMPERATURE <= temperature <= self.MAX_TEMPERATURE:
            raise ValueError(
                f"Temperature {temperature} is out of range for OpenAI "
                f"({self.MIN_TEMPERATURE} to {self.MAX_TEMPERATURE})."
            )

    def create_agent(self, agent: AgentDefinition) -> None:
        self._validate_model(agent.model)
        self._validate_temperature(agent.temperature)

    def change_model(self, agent: AgentDefinition, new_model: str) -> None:
        self._validate_model(new_model)
