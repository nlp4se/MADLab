from dataclasses import replace

from .contracts.external_agent_manager import ExternalAgentManager
from .contracts.agent_record import AgentRecord, AgentDefinition
from .contracts.prompt_record import PromptRecord


class AgentManager:
    def __init__(self, agent_name: str,
                 external_manager: ExternalAgentManager,
                 agent_record: AgentRecord,
                 prompt_record: PromptRecord):
        self.agent_name = agent_name
        self.external_manager = external_manager
        self.agent_record = agent_record
        self.prompt_record = prompt_record

    def setup_agent(self, prompt_path: str, model: str,
                    temperature: float = 0.0, schema_file_path: str = None) -> None:
        instructions = self.prompt_record.get(prompt_path)
        agent = AgentDefinition(
            name=self.agent_name,
            model=model,
            instructions=instructions,
            temperature=temperature,
            schema_file_path=schema_file_path,
        )
        self.external_manager.create_agent(agent)
        self.agent_record.save(agent)

    def get_model(self) -> str:
        agent = self.agent_record.get(self.agent_name)
        return self.external_manager.get_model(agent)

    def change_model(self, new_model: str) -> None:
        agent = self.agent_record.get(self.agent_name)
        self.external_manager.change_model(agent, new_model)
        self.agent_record.save(replace(agent, model=new_model))

    def delete_agent(self) -> None:
        agent = self.agent_record.get(self.agent_name)
        self.external_manager.delete_agent(agent)
        self.agent_record.delete(self.agent_name)

    def list_agent_records(self) -> None:
        agent_record_names = self.agent_record.list_names()
        print("AgentRecords:")
        for record_name in agent_record_names:
            print(f"Name: {record_name}")
        if not agent_record_names:
            print("No AgentRecords were found in local storage.")
