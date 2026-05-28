from .contracts.external_agent_manager import ExternalAgentManager
from .contracts.agent_record import AgentRecord
from .contracts.prompt_record import PromptRecord


class AgentManager:
    def __init__(self, assistant_name: str,
                 external_manager: ExternalAgentManager,
                 agent_record: AgentRecord,
                 prompt_record: PromptRecord):
        self.assistant_name = assistant_name
        self.external_manager = external_manager
        self.agent_record = agent_record
        self.prompt_record = prompt_record

    def setup_assistant(self, prompt_path: str, model: str, **kwargs) -> None:
        instructions = self.prompt_record.get(prompt_path)
        assistant_id = self.external_manager.create_assistant(
            self.assistant_name, instructions, model, **kwargs
        )
        self.agent_record.create(self.assistant_name, assistant_id)

    def get_model(self) -> str:
        assistant_id = self.agent_record.get_id(self.assistant_name)
        return self.external_manager.get_model(assistant_id)

    def change_model(self, new_model: str) -> None:
        assistant_id = self.agent_record.get_id(self.assistant_name)
        self.external_manager.change_model(assistant_id, new_model)

    def delete_assistant(self) -> None:
        assistant_id = self.agent_record.get_id(self.assistant_name)
        self.external_manager.delete_assistant(assistant_id)
        self.agent_record.delete(self.assistant_name)

    def list_agent_records(self) -> None:
        agent_record_names = self.agent_record.list_names()
        print("AgentRecords:")
        for record_name in agent_record_names:
            print(f"Name: {record_name}")
        if not agent_record_names:
            print("No AgentRecords were found in local storage.")

    def delete_invalid_agent_records(self) -> None:
        openai_assistants = self.external_manager.list_assistants()

        print("OpenAI Assistants found:")
        for name, ids in openai_assistants.items():
            print(f"  {name}: {sorted(ids)}")

        agent_record_names = self.agent_record.list_names()
        print("\nAgentRecords found in local storage:")
        for name in agent_record_names:
            stored_id = self.agent_record.get_id(name)
            print(f"  {name}: {stored_id}")

        no_name_match = []
        id_mismatch = []
        for name in agent_record_names:
            if name not in openai_assistants:
                no_name_match.append(name)
            elif self.agent_record.get_id(name) not in openai_assistants[name]:
                id_mismatch.append(name)

        print("\nAgentRecords deleted (name not found in OpenAI):")
        for name in no_name_match:
            print(f"  {name}")
            self.agent_record.delete(name)

        print("\nAgentRecords deleted (name exists in OpenAI but stored ID does not match any of its IDs):")
        for name in id_mismatch:
            stored_id = self.agent_record.get_id(name)
            print(f"  {name}: local={stored_id}, OpenAI={sorted(openai_assistants[name])}")
            self.agent_record.delete(name)
