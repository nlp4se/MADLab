from typing import List, Dict, Tuple
import argparse
import os
from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
import json
from tqdm import tqdm

from .openai.ask_assistant_openai import OpenAIAssistantCaller

load_dotenv()

class LLMCoordinator:
    def __init__(self, api_key: str):
        """Initialize the coordinator with an API key."""
        self.caller = OpenAIAssistantCaller(api_key=api_key)

    def judge_approach(
        self,
        requirement: str,
        assistants: List[Tuple[str, str]],
        judge: Tuple[str, str],
        temperature: float = 0
    ) -> Tuple[str, Dict]:
        """
        Process a single requirement through assistants and judge.
        
        Args:
            requirement: The requirement text
            assistants: List of (assistant_name, model) pairs
            judge: Tuple of (judge_name, model)
            temperature: Temperature for generation
            
        Returns:
            Tuple of (judge_decision, metrics)
        """
        responses = []
        total_metrics = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        }

        # Get responses from assistants
        for assistant_name, model in assistants:
            response, metrics = self.caller.send_message(
                requirement,
                assistant_name=assistant_name,
                model=model,
                temperature=temperature
            )
            responses.append((assistant_name, response))
            
            # Accumulate metrics
            for key in total_metrics:
                total_metrics[key] += metrics[key]

        # Prepare input for judge
        assistant_responses = "\n\n".join([
            f"Assistant '{name}' response:\n{response}"
            for name, response in responses
        ])
        judge_input = f"Requirement: {requirement}\n\n{assistant_responses}"

        # Get judge's decision
        judge_name, judge_model = judge
        raw_decision, judge_metrics = self.caller.send_message(
            judge_input,
            assistant_name=judge_name,
            model=judge_model,
            temperature=temperature
        )

        # Parse the JSON response and extract the class value
        try:
            decision_obj = json.loads(raw_decision)
            decision = decision_obj['class']
            justification = decision_obj['justification']
        except (json.JSONDecodeError, KeyError) as e:
            raise Exception(f"Invalid judge response format: {raw_decision}") from e

        # Add judge metrics
        for key in total_metrics:
            total_metrics[key] += judge_metrics[key]

        return decision, justification, total_metrics

    def process_dataset(
        self,
        input_file: Path,
        output_file: Path,
        assistants: List[Tuple[str, str]],
        judge: Tuple[str, str],
        temperature: float = 0
    ) -> None:
        """Process entire dataset through assistants and judge."""
        df = pd.read_csv(input_file)
        df['judge'] = ''
        total_metrics = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}

        # Add progress bar
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing requirements"):
            requirement = row['requirement']
            if not isinstance(requirement, str) or not requirement.strip():
                continue

            try:
                decision, justification, metrics = self.judge_approach(
                    requirement,
                    assistants,
                    judge,
                    temperature
                )
                df.at[idx, 'judge'] = decision
                df.at[idx, 'justification'] = justification
                # Accumulate metrics
                for key in total_metrics:
                    total_metrics[key] += metrics[key]

            except Exception as e:
                print(f"Error processing requirement {idx}: {str(e)}")

        df.to_csv(output_file, index=False)
        print("\nTotal token usage:", total_metrics)

def main():
    parser = argparse.ArgumentParser(description='Process requirements through assistants and judge')
    parser.add_argument('--input', type=Path, required=True, help='Input CSV file path')
    parser.add_argument('--output', type=Path, required=True, help='Output CSV file path')
    parser.add_argument('--assistants-file', type=Path, required=True, help='JSON file with assistant configs')
    parser.add_argument('--judge-file', type=Path, required=True, help='JSON file with judge config')
    parser.add_argument('--temperature', type=float, default=0, help='Temperature for generation')
    args = parser.parse_args()

    # Initialize coordinator
    coordinator = LLMCoordinator(api_key=os.getenv("OPENAI_API_KEY"))

    # Load configurations
    with open(args.assistants_file) as f:
        assistants = json.load(f)  # Expected: [["assistant1_name", "model1"], ...]
    with open(args.judge_file) as f:
        judge = json.load(f)  # Expected: ["judge_name", "model"]

    coordinator.process_dataset(
        args.input,
        args.output,
        assistants,
        judge,
        args.temperature
    )

if __name__ == "__main__":
    main()
