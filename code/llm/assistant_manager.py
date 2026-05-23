from abc import ABC, abstractmethod
from typing import Any

from ..persistence.assistant_file import AssistantFile
from ..persistence.prompt_file import PromptFile


class AssistantManager(ABC):
    def __init__(self, api_key: str, assistant_name: str,
                 assistant_file: AssistantFile, prompt_file: PromptFile):
        self.api_key = api_key
        self.assistant_name = assistant_name
        self.assistant_file = assistant_file
        self.prompt_file = prompt_file
        self.client = self._initialize_client()

    @abstractmethod
    def _initialize_client(self) -> Any:
        pass

    def setup_assistant(self, prompt_path: str, model: str, **kwargs) -> None:
        instructions = self.prompt_file.get_prompt(prompt_path)
        assistant_id = self.create_assistant(instructions, model, **kwargs)
        self.assistant_file.create_assistant_record(self.assistant_name, assistant_id)

    @abstractmethod
    def create_assistant(self, instructions: str, model: str, **kwargs) -> str:
        pass

    @abstractmethod
    def change_model_service(self, assistant_id: str, new_model: str) -> None:
        pass

    def change_model(self, new_model: str) -> None:
        assistant_id = self.assistant_file.get_assistant_record_id(self.assistant_name)
        self.change_model_service(assistant_id, new_model)

    @abstractmethod
    def delete_assistant_service(self, assistant_id: str) -> None:
        pass

    def delete_assistant(self) -> None:
        assistant_id = self.assistant_file.get_assistant_record_id(self.assistant_name)
        self.delete_assistant_service(assistant_id)
        self.assistant_file.delete_assistant_record(self.assistant_name)
