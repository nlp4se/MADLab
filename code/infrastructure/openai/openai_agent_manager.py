import os
import json
from openai import OpenAI, NotFoundError, BadRequestError
from typing import Dict

from ...core.ports.external_agent_manager import ExternalAgentManager


class OpenAIAgentManager(ExternalAgentManager):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

    def _get_json_schema(self, schema_file_path: str = None) -> Dict:
        if schema_file_path and os.path.exists(schema_file_path):
            with open(schema_file_path, 'r', encoding='utf-8') as f:
                return {"type": "json_schema", "json_schema": json.loads(f.read())}
        return None

    def create_assistant(self, name: str, instructions: str, model: str = "gpt-4o", **kwargs) -> str:
        temperature = kwargs.get('temperature', 0.0)
        schema_file_path = kwargs.get('schema_file_path', None)

        print("Creating a new OpenAI Assistant...")
        assistant = self.client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model,
            temperature=temperature,
            response_format=self._get_json_schema(schema_file_path)
        )
        print(f"OpenAI Assistant created successfully. ID: {assistant.id} with Model: {model}")
        return assistant.id

    def get_model(self, assistant_id: str) -> str:
        try:
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            return assistant.model
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant with ID '{assistant_id}' not found in OpenAI. "
                f"The AgentRecord may be stale. Run 'delete-invalid' to clean up orphaned AgentRecords."
            )

    def change_model(self, assistant_id: str, new_model: str) -> None:
        try:
            self.client.beta.assistants.update(assistant_id, model=new_model)
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant with ID '{assistant_id}' not found in OpenAI. "
                f"The AgentRecord may be stale. Run 'delete-invalid' to clean up orphaned AgentRecords."
            )

    def delete_assistant(self, assistant_id: str) -> None:
        try:
            self.client.beta.assistants.delete(assistant_id)
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant with ID '{assistant_id}' not found in OpenAI. "
                f"The AgentRecord may be stale. Run 'delete-invalid' to clean up orphaned AgentRecords."
            )
        except BadRequestError as e:
            if e.code == 'invalid_value':
                raise ValueError(
                    f"The AgentRecord contains an invalid OpenAI Assistant ID: '{assistant_id}'. "
                    f"The record is corrupted. Run 'delete-invalid' to clean up orphaned AgentRecords."
                )
            raise

    def list_assistants(self) -> dict[str, set[str]]:
        openai_assistants: dict[str, set[str]] = {}
        page = self.client.beta.assistants.list(limit=100)
        while True:
            for assistant in page.data:
                openai_assistants.setdefault(assistant.name, set()).add(assistant.id)
            if not page.has_next_page():
                break
            page = page.get_next_page()
        return openai_assistants
