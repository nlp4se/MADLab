import os
import argparse
from dotenv import load_dotenv

from code.domain.agent_manager import AgentManager
from code.infrastructure.openai.openai_agent_manager import OpenAIAgentManager
from code.infrastructure.persistence.file_agent_record import FileAgentRecord
from code.infrastructure.persistence.file_prompt_record import FilePromptRecord


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Manage OpenAI Assistants and local AgentRecords.')
    subparsers = parser.add_subparsers(dest='action', required=True)

    create_parser = subparsers.add_parser('create', help='Create a new OpenAI Assistant and register its AgentRecord')
    create_parser.add_argument('--agent-name', required=True, help='Name of the OpenAI Assistant / AgentRecord')
    create_parser.add_argument('--prompt-path', required=True,
                               help='Prompt path relative to data/prompts/')
    create_parser.add_argument('--model', default="gpt-4o", help='OpenAI model to use')
    create_parser.add_argument('--temperature', type=float, default=0.0, help='Temperature (0.0 to 2.0)')
    create_parser.add_argument('--schema-file-path', help='Path to JSON schema file')

    delete_parser = subparsers.add_parser('delete', help='Delete an existing OpenAI Assistant and its AgentRecord')
    delete_parser.add_argument('--agent-name', required=True, help='Name of the OpenAI Assistant / AgentRecord')

    change_model_parser = subparsers.add_parser('change-model', help='Change the model of an existing OpenAI Assistant')
    change_model_parser.add_argument('--agent-name', required=True, help='Name of the OpenAI Assistant')
    change_model_parser.add_argument('--model', required=True, help='New OpenAI model to use')

    get_model_parser = subparsers.add_parser('get-model', help='Get the current model of an OpenAI Assistant')
    get_model_parser.add_argument('--agent-name', required=True, help='Name of the OpenAI Assistant')

    subparsers.add_parser('get-all', help='List all local AgentRecords')
    subparsers.add_parser('delete-invalid', help='Delete local AgentRecords whose OpenAI Assistant is missing or whose stored ID does not match any of the IDs OpenAI has for that name')

    args = parser.parse_args()

    agent_name = getattr(args, 'agent_name', None)
    external_manager = OpenAIAgentManager(api_key=os.getenv("OPENAI_API_KEY"))
    agent_record = FileAgentRecord()
    prompt_record = FilePromptRecord()
    manager = AgentManager(
        agent_name=agent_name,
        external_manager=external_manager,
        agent_record=agent_record,
        prompt_record=prompt_record,
    )

    if args.action == 'create':
        manager.setup_agent(
            prompt_path=args.prompt_path,
            model=args.model,
            temperature=args.temperature,
            schema_file_path=args.schema_file_path
        )
    elif args.action == 'delete':
        manager.delete_agent()
    elif args.action == 'change-model':
        manager.change_model(args.model)
        print(f"Model updated to '{args.model}' for OpenAI Assistant '{args.agent_name}'")
    elif args.action == 'get-model':
        model = manager.get_model()
        print(f"OpenAI Assistant '{args.agent_name}' is using model: '{model}'")
    elif args.action == 'get-all':
        manager.list_agent_records()
    elif args.action == 'delete-invalid':
        manager.delete_invalid_agent_records()


if __name__ == "__main__":
    main()
