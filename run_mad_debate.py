import sys
import os
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv

from code.core.mad_debate import MadDebate
from code.core.agent_caller import AgentCaller
from code.core.validators import validate_interaction_file
from code.infrastructure.openai.openai_agent_caller import OpenAIAgentCaller
from code.infrastructure.persistence.file_agent_record import FileAgentRecord
from code.infrastructure.pubsub.pubsub_event_bus import PubSubEventBus


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Process requirements through assistants and judge')
    parser.add_argument('--input', type=Path, required=True, help='Input CSV file path')
    parser.add_argument('--output', type=Path, required=True, help='Output CSV file path')
    parser.add_argument('--judge-file', type=Path, required=True, help='JSON file with judge config')
    parser.add_argument('--temperature', type=float, default=0, help='Temperature for generation')
    parser.add_argument('--interaction-file', type=Path, required=True, help='JSON file with topology and protocol config')
    args = parser.parse_args()

    agent_record = FileAgentRecord()
    external_caller = OpenAIAgentCaller(api_key=os.getenv("OPENAI_API_KEY"))
    caller = AgentCaller(external_caller=external_caller, agent_record=agent_record)
    event_bus = PubSubEventBus()
    debate = MadDebate(caller=caller, event_bus=event_bus)

    with open(args.interaction_file) as f:
        interaction_config = json.load(f)

    try:
        validate_interaction_file(interaction_config)
    except ValueError as e:
        if str(e).startswith("Configuration Error:"):
            print(f"\n{e}")
            sys.exit(1)
        else:
            raise

    turns = interaction_config.get("turns", [])

    if isinstance(turns, dict):
        iterations = len(turns.keys()) - 1
    else:
        iterations = interaction_config.get("number_of_rounds", 0) - 1

    assistants = interaction_config["assistants"]
    topology = interaction_config["topology"]

    with open(args.judge_file) as f:
        judge_config = json.load(f)

    judge = judge_config['judge_name']

    debate.process_dataset(
        args.input,
        args.output,
        assistants,
        topology,
        turns,
        judge,
        args.temperature,
        n_iterations=iterations
    )


if __name__ == "__main__":
    main()
