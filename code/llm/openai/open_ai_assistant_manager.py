import os
import argparse
import json
from openai import OpenAI, NotFoundError, BadRequestError
from typing import Dict, Any
from dotenv import load_dotenv

from ..assistant_manager import AssistantManager
from ...persistence.assistant_file import AssistantFile
from ...persistence.prompt_file import PromptFile


class OpenAIAssistantManager(AssistantManager):
    def _initialize_client(self) -> OpenAI:
        return OpenAI(api_key=self.api_key)

    def get_json_schema(self, schema_file_path: str = None) -> Dict:
        if schema_file_path and os.path.exists(schema_file_path):
            with open(schema_file_path, 'r', encoding='utf-8') as f:
                return {"type": "json_schema", "json_schema": json.loads(f.read())}
        return None

    def get_model(self) -> str:
        assistant_id = self.assistant_file.get_assistant_record_id(self.assistant_name)
        try:
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            return assistant.model
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant referenced by AssistantRecord '{self.assistant_name}' (ID: '{assistant_id}') not found in OpenAI. "
                f"The AssistantRecord may be stale. Run 'delete-invalid' to clean up orphaned records."
            )

    def create_assistant(self, instructions: str, model: str = "gpt-4o", **kwargs) -> str:
        temperature = kwargs.get('temperature', 0.0)
        schema_file_path = kwargs.get('schema_file_path', None)

        print("Creating a new OpenAI Assistant...")
        assistant = self.client.beta.assistants.create(
            name=self.assistant_name,
            instructions=instructions,
            model=model,
            temperature=temperature,
            response_format=self.get_json_schema(schema_file_path)
        )
        print(f"OpenAI Assistant created successfully. ID: {assistant.id} with Model: {model}")
        return assistant.id

    def change_model_service(self, assistant_id: str, new_model: str) -> None:
        try:
            self.client.beta.assistants.update(assistant_id, model=new_model)
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant referenced by AssistantRecord '{self.assistant_name}' (ID: '{assistant_id}') not found in OpenAI. "
                f"The AssistantRecord may be stale. Run 'delete-invalid' to clean up orphaned records."
            )

    def delete_assistant_service(self, assistant_id: str) -> None:
        try:
            self.client.beta.assistants.delete(assistant_id)
        except NotFoundError:
            raise ValueError(
                f"OpenAI Assistant referenced by AssistantRecord '{self.assistant_name}' (ID: '{assistant_id}') not found in OpenAI. "
                f"The AssistantRecord may be stale. Run 'delete-invalid' to clean up orphaned records."
            )
        except BadRequestError as e:
            if e.code == 'invalid_value':
                raise ValueError(
                    f"AssistantRecord '{self.assistant_name}' contains an invalid OpenAI Assistant ID: '{assistant_id}'. "
                    f"The record is corrupted. Run 'delete-invalid' to clean up orphaned records."
                )
            raise
        
    def get_all_assistant_records(self) -> None:
        assistant_records = self.assistant_file.get_all_assistant_records()
        print(f"AssistantRecords:")
        for record_name in assistant_records:
            print(f"Name: {record_name}")
        if not assistant_records:
            print("No AssistantRecords were found in local storage.")

    def delete_invalid_assistants(self) -> None:
        openai_assistants: dict[str, set[str]] = {}
        page = self.client.beta.assistants.list(limit=100)
        while True:
            for assistant in page.data:
                openai_assistants.setdefault(assistant.name, set()).add(assistant.id)
            if not page.has_next_page():
                break
            page = page.get_next_page()
        print("OpenAI Assistants found:")
        for name, ids in openai_assistants.items():
            print(f"  {name}: {sorted(ids)}")

        assistant_records = self.assistant_file.get_all_assistant_records()
        print("\nAssistantRecords found in local storage:")
        for name in assistant_records:
            stored_id = self.assistant_file.get_assistant_record_id(name)
            print(f"  {name}: {stored_id}")

        no_name_match = []
        id_mismatch = []
        for name in assistant_records:
            if name not in openai_assistants:
                no_name_match.append(name)
            elif self.assistant_file.get_assistant_record_id(name) not in openai_assistants[name]:
                id_mismatch.append(name)

        print("\nAssistantRecords deleted (name not found in OpenAI):")
        for name in no_name_match:
            print(f"  {name}")
            self.assistant_file.delete_assistant_record(name)

        print("\nAssistantRecords deleted (ID mismatch):")
        for name in id_mismatch:
            stored_id = self.assistant_file.get_assistant_record_id(name)
            print(f"  {name}: local={stored_id}, OpenAI={sorted(openai_assistants[name])}")
            self.assistant_file.delete_assistant_record(name)
      


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Manage OpenAI Assistants and local AssistantRecords.')
    subparsers = parser.add_subparsers(dest='action', required=True)

    create_parser = subparsers.add_parser('create', help='Create a new OpenAI Assistant and register its AssistantRecord')
    create_parser.add_argument('--assistant-name', required=True, help='Name of the OpenAI Assistant / AssistantRecord')
    create_parser.add_argument('--prompt-path', required=True,
                               help='Prompt path relative to data/prompts/')
    create_parser.add_argument('--model', default="gpt-4o", help='OpenAI model to use')
    create_parser.add_argument('--temperature', type=float, default=0.0, help='Temperature (0.0 to 2.0)')
    create_parser.add_argument('--schema-file-path', help='Path to JSON schema file')

    delete_parser = subparsers.add_parser('delete', help='Delete an existing OpenAI Assistant and its AssistantRecord')
    delete_parser.add_argument('--assistant-name', required=True, help='Name of the OpenAI Assistant / AssistantRecord')

    change_model_parser = subparsers.add_parser('change-model', help='Change the model of an existing OpenAI Assistant')
    change_model_parser.add_argument('--assistant-name', required=True, help='Name of the OpenAI Assistant')
    change_model_parser.add_argument('--model', required=True, help='New OpenAI model to use')

    get_model_parser = subparsers.add_parser('get-model', help='Get the current model of an OpenAI Assistant')
    get_model_parser.add_argument('--assistant-name', required=True, help='Name of the OpenAI Assistant')

    get_all_parser = subparsers.add_parser('get-all', help='List all local AssistantRecords')
    delete_invalid_parser = subparsers.add_parser('delete-invalid', help='Delete AssistantRecords with no matching OpenAI Assistant')


    args = parser.parse_args()

    assistant_name = getattr(args, 'assistant_name', None)
    manager = OpenAIAssistantManager(
        api_key=os.getenv("OPENAI_API_KEY"),
        assistant_name=assistant_name,
        assistant_file=AssistantFile(),
        prompt_file=PromptFile()
    )

    if args.action == 'create':
        manager.setup_assistant(
            prompt_path=args.prompt_path,
            model=args.model,
            temperature=args.temperature,
            schema_file_path=args.schema_file_path
        )
    elif args.action == 'delete':
        manager.delete_assistant()
    elif args.action == 'change-model':
        manager.change_model(args.model)
        print(f"Model updated to '{args.model}' for OpenAI Assistant '{args.assistant_name}'")
    elif args.action == 'get-model':
        model = manager.get_model()
        print(f"OpenAI Assistant '{args.assistant_name}' is using model: '{model}'")
    elif args.action == 'get-all':
        manager.get_all_assistant_records()
    elif args.action == 'delete-invalid':
        manager.delete_invalid_assistants()

if __name__ == "__main__":
    main()
