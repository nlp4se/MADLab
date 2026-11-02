from dataclasses import replace

from openai import OpenAI, OpenAIError

from ...domain.contracts.external_agent_manager import ExternalAgentManager
from ...domain.contracts.agent_record import AgentDefinition
from .openai_agent_caller import build_text_format


class OpenAIAgentManager(ExternalAgentManager):
    MIN_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 2.0

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

    def _validate_agent(self, agent: AgentDefinition) -> None:
        try:
            self.client.responses.create(
                model=agent.model,
                instructions=agent.instructions,
                input="ping",
                temperature=agent.temperature,
                text=build_text_format(agent.schema_file_path),
                max_output_tokens=16,
                store=False,
            )
        except OpenAIError as e:
            raise ValueError(f"OpenAI rejected agent '{agent.name}' (model '{agent.model}'): {e}")

    def _validate_temperature(self, temperature: float) -> None:
        if not self.MIN_TEMPERATURE <= temperature <= self.MAX_TEMPERATURE:
            raise ValueError(
                f"Temperature {temperature} is out of range for OpenAI "
                f"({self.MIN_TEMPERATURE} to {self.MAX_TEMPERATURE})."
            )

    def create_agent(self, agent: AgentDefinition) -> None:
        self._validate_temperature(agent.temperature)
        self._validate_agent(agent)

    def change_model(self, agent: AgentDefinition, new_model: str) -> None:
        self._validate_agent(replace(agent, model=new_model))
