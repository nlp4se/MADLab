from typing import List, Dict, Tuple
import argparse
import os
from dotenv import load_dotenv
import pandas as pd
from pathlib import Path
import json
from tqdm import tqdm
import time

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
        temperature: float = 0,
        n_iterations: int = 0
    ) -> Tuple[str, Dict]:
        """Process a single requirement through assistants and judge."""
        start_time = time.time()
        responses = []
        total_metrics = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'execution_time': 0
        }

        print("\n" + "="*80)
        print(f"Processing requirement: {requirement}\n")

        # Initial responses from assistants
        print("Initial round responses:")
        print("-"*40)
        initial_responses = []
        for assistant_name, model in assistants:
            response, metrics = self.caller.send_message(
                requirement,
                assistant_name=assistant_name,
                model=model,
                temperature=temperature
            )
            print(f"\nAssistant '{assistant_name}':\n{response}")
            initial_responses.append((assistant_name, response))
            responses.append((assistant_name, response, 0))
            
            for key in total_metrics:
                if key != 'execution_time':
                    total_metrics[key] += metrics[key]

        # Iterate for n rounds if n > 0
        current_responses = initial_responses
        for iteration in range(n_iterations):
            print(f"\nIteration {iteration + 1} responses:")
            print("-"*40)
            new_responses = []
            for idx, (assistant_name, model) in enumerate(assistants):
                other_responses = "\n\n".join([
                    f"Assistant '{name}' response:\n{resp}"
                    for name, resp in current_responses if name != assistant_name
                ])
                
                debate_input = f"Requirement: {requirement}\n\nOpposing arguments:\n{other_responses}"
                
                response, metrics = self.caller.send_message(
                    debate_input,
                    assistant_name=assistant_name,
                    model=model,
                    temperature=temperature
                )
                print(f"\nAssistant '{assistant_name}':\n{response}")
                new_responses.append((assistant_name, response))
                responses.append((assistant_name, response, iteration + 1))
                
                for key in total_metrics:
                    if key != 'execution_time':
                        total_metrics[key] += metrics[key]
            
            current_responses = new_responses

        # Get judge's decision for each iteration level
        decisions = {}
        judge_metrics = {}
        judge_name, judge_model = judge
        
        print("\nJudge decisions:")
        print("-"*40)
        for n in range(n_iterations + 1):
            filtered_responses = [r for r in responses if r[2] <= n]
            discussion_history = "\n\n".join([
                f"Round {round_num} - Assistant '{name}' response:\n{response}"
                for name, response, round_num in filtered_responses
            ])
            
            judge_input = f"Requirement: {requirement}\n\n{discussion_history}"
            
            raw_decision, metrics = self.caller.send_message(
                judge_input,
                assistant_name=judge_name,
                model=judge_model,
                temperature=temperature
            )

            try:
                decision_obj = json.loads(raw_decision)
                decisions[n] = decision_obj['class']
                judge_metrics[n] = metrics
                print(f"\nFor iteration {n}:")
                print(f"Decision: {decision_obj['class']}")
                print(f"Raw response: {raw_decision}")
                
                for key in total_metrics:
                    if key != 'execution_time':
                        total_metrics[key] += metrics[key]
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Invalid judge response format: {raw_decision}") from e

        total_metrics['execution_time'] = time.time() - start_time
        print("\n" + "="*80)
        return decisions, total_metrics

    def process_dataset(
        self,
        input_file: Path,
        output_file: Path,
        assistants: List[Tuple[str, str]],
        judge: Tuple[str, str],
        temperature: float = 0,
        n_iterations: int = 0
    ) -> None:
        """Process entire dataset through assistants and judge."""
        df = pd.read_csv(input_file)
        df['judge'] = ''
        
        # Create output files for each iteration
        output_files = {}
        metrics_files = {}
        for n in range(n_iterations + 1):
            # Create output file names with iteration number
            base_name = output_file.stem
            output_path = output_file.parent / f"{base_name}_n{n}{output_file.suffix}"
            metrics_path = output_file.parent / f"{base_name}_metrics_n{n}.json"
            
            # Initialize files
            df.head(0).to_csv(output_path, index=False)
            output_files[n] = output_path
            metrics_files[n] = metrics_path
            
            # Initialize metrics tracking for each iteration
            with open(metrics_path, 'w') as f:
                json.dump({
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'execution_time': 0,
                    'requirements_processed': 0
                }, f)

        # Add progress bar
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Processing requirements"):
            requirement = row['requirement']
            if not isinstance(requirement, str) or not requirement.strip():
                continue

            try:
                decisions, metrics = self.judge_approach(
                    requirement,
                    assistants,
                    judge,
                    temperature,
                    n_iterations
                )
                
                # Save results for each iteration
                for n in range(n_iterations + 1):
                    # Save decision
                    row_copy = row.copy()
                    row_copy['judge'] = decisions[n]
                    pd.DataFrame([row_copy]).to_csv(output_files[n], mode='a', header=False, index=False)
                    
                    # Update metrics file with cumulative metrics
                    with open(metrics_files[n], 'r') as f:
                        current_metrics = json.load(f)
                    
                    # Calculate execution time up to this iteration
                    iteration_time = metrics['execution_time'] * (n + 1) / (n_iterations + 1)
                    
                    # Update metrics
                    for key in metrics:
                        if key == 'execution_time':
                            current_metrics[key] += iteration_time
                        else:
                            # For token metrics, add proportional amount based on iteration
                            current_metrics[key] += metrics[key] * (n + 1) / (n_iterations + 1)
                    
                    current_metrics['requirements_processed'] += 1
                    
                    with open(metrics_files[n], 'w') as f:
                        json.dump(current_metrics, f)

            except Exception as e:
                print(f"Error processing requirement {idx}: {str(e)}")

        # Print final metrics for all iterations
        print("\nFinal metrics for each iteration:")
        for n in range(n_iterations + 1):
            with open(metrics_files[n], 'r') as f:
                metrics = json.load(f)
            print(f"\nIteration {n}:", metrics)

def main():
    parser = argparse.ArgumentParser(description='Process requirements through assistants and judge')
    parser.add_argument('--input', type=Path, required=True, help='Input CSV file path')
    parser.add_argument('--output', type=Path, required=True, help='Output CSV file path')
    parser.add_argument('--assistants-file', type=Path, required=True, help='JSON file with assistant configs')
    parser.add_argument('--judge-file', type=Path, required=True, help='JSON file with judge config')
    parser.add_argument('--temperature', type=float, default=0, help='Temperature for generation')
    parser.add_argument('--n', type=int, help='Number of requirements to sample per class (optional)')
    parser.add_argument('--iterations', type=int, default=0, help='Number of debate iterations')
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
        args.temperature,
        n_iterations=args.iterations
    )

if __name__ == "__main__":
    main()
