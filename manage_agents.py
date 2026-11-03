import os
import argparse
from dotenv import load_dotenv

from code.domain.agent_manager import AgentManager
from code.infrastructure.openai.openai_agent_manager import OpenAIAgentManager
from code.infrastructure.persistence.file_agent_record import FileAgentRecord
from code.infrastructure.persistence.file_prompt_record import FilePromptRecord


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Manage agents and their local AgentRecords.')
    subparsers = parser.add_subparsers(dest='action', required=True)

    create_parser = subparsers.add_parser('create', help='Create a new agent and save its AgentRecord')
    create_parser.add_argument('--agent-name', required=True, help='Name of the agent / AgentRecord')
    create_parser.add_argument('--prompt-path', required=True,
                               help='Prompt path relative to data/prompts/')
    create_parser.add_argument('--model', default="gpt-4o", help='Model to use')
    create_parser.add_argument('--temperature', type=float, default=0.0, help='Temperature (valid range depends on the provider)')
    create_parser.add_argument('--schema-file-path', help='Path to JSON schema file')

    delete_parser = subparsers.add_parser('delete', help='Delete an existing agent and its AgentRecord')
    delete_parser.add_argument('--agent-name', required=True, help='Name of the agent / AgentRecord')

    change_model_parser = subparsers.add_parser('change-model', help='Change the model of an existing agent')
    change_model_parser.add_argument('--agent-name', required=True, help='Name of the agent')
    change_model_parser.add_argument('--model', required=True, help='New model to use')

    get_model_parser = subparsers.add_parser('get-model', help='Get the current model of an agent')
    get_model_parser.add_argument('--agent-name', required=True, help='Name of the agent')

    subparsers.add_parser('get-all', help='List all local AgentRecords')

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
        print(f"Model updated to '{args.model}' for agent '{args.agent_name}'")
    elif args.action == 'get-model':
        model = manager.get_model()
        print(f"Agent '{args.agent_name}' is using model: '{model}'")
    elif args.action == 'get-all':
        manager.list_agent_records()


if __name__ == "__main__":
    main()
