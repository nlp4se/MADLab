from abc import ABC, abstractmethod
from typing import Any
import os

class AssistantCreator(ABC):
    """Abstract base class for creating AI assistants."""
    
    def __init__(self, api_key: str, assistant_name: str, prompt_file_path: str):
        self.api_key = api_key
        self.assistant_name = assistant_name
        self.prompt_file_path = prompt_file_path
        self.client = self._initialize_client()
    
    @abstractmethod
    def _initialize_client(self) -> Any:
        """Initialize the specific AI provider's client."""
        pass
    
    def save_assistant_id(self, assistant_id: str, model: str):
        """Save the assistant ID to a file for reuse."""
        filename = f"data/assistants/assistant_{self.assistant_name}_{model}.txt"
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w') as file:
            file.write(assistant_id)
    
    def get_base_instructions(self) -> str:
        """Get the base instructions template."""
        with open(self.prompt_file_path, 'r') as f:
            system_prompt = f.read()
        
        return system_prompt.format(assistant_name=self.assistant_name)
    
    @abstractmethod
    def create_assistant(self, guidelines_file: str, model: str) -> Any:
        """Create an AI assistant with the specified guidelines and model."""
        pass 