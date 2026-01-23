from typing import List, Dict, Tuple, Optional
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



class InteractionProtocol:

    STRATEGIES = {
        'simultaneous': 'simultaneous_protocol_interaction',
        'sequential': 'sequential_protocol_interaction',
    }
    assigned_strategy: str


    def __init__(self, caller, protocol_type: str):
        self.caller = caller
        self.assigned_strategy = protocol_type


    def run(
        self, 
        assistants: List[Tuple[str, str]],
        assistant_threads: Dict[str, str],
        requirement: str,
        temperature: float,
        responses: List[Tuple[str, str, int]],
        total_metrics: Dict[str, float],
        n_iterations: int
    ):

        method_name = self.STRATEGIES[self.assigned_strategy]
        method = getattr(self, method_name)

        return method(
            assistants,
            assistant_threads,
            requirement,
            temperature,
            responses,
            total_metrics,
            n_iterations
        )


    def simultaneous_protocol_interaction(
        self,
        assistants: List[Tuple[str, str]],
        assistant_threads: Dict[str, str],
        requirement: str,
        temperature: float,
        responses: List[Tuple[str, str, int]],
        total_metrics: Dict[str, float],
        n_iterations: int
    ):
        print("Initial round responses:")
        print("-"*40)
        initial_responses = []
        for assistant_name, model in assistants:
            thread_id = assistant_threads[assistant_name]
            print("*"*40)
            print(f"\nInput to Assistant '{assistant_name}' [Thread ID: {thread_id}]:")
            print(f"{requirement}")
            print("\nResponse:")

            result_assistant_name, result_response, result_number_iteration = self.assistant_response(
                thread_id,
                requirement,
                assistant_name,
                model,
                temperature,
                total_metrics,
                0,
            )
            responses.append((result_assistant_name, result_response, result_number_iteration))

        # Iterate for n rounds if n > 0
        current_responses = [(name, resp) for name, resp, _ in responses]

        for iteration in range(n_iterations):
            print(f"\nIteration {iteration + 1} responses:")
            print("-"*40)
            new_responses = []
            for idx, (assistant_name, model) in enumerate(assistants):
                thread_id = assistant_threads[assistant_name]
                # Get the most recent responses from other assistants
                other_responses = "\n\n".join([
                    f"Assistant '{name}' response:\n{resp}"
                    for name, resp in current_responses if name != assistant_name
                ])
                
                # For subsequent iterations, only provide opposing arguments
                debate_input = f"Opposing arguments:\n\n{other_responses}"

                print("*"*40)
                print(f"\nInput to Assistant '{assistant_name}' [Thread ID: {thread_id}]:")
                print(f"{debate_input}")
                print("\nResponse:")

                result_assistant_name, result_response, result_number_iteration = self.assistant_response(
                    thread_id,
                    debate_input,
                    assistant_name,
                    model,
                    temperature,
                    total_metrics,
                    iteration + 1,
                ) 
                responses.append((result_assistant_name, result_response, result_number_iteration))
                new_responses.append((result_assistant_name, result_response))

            current_responses = new_responses

    def sequential_protocol_interaction(
        self,
        assistants: List[Tuple[str, str]],
        assistant_threads: Dict[str, str],
        requirement: str,
        temperature: float,
        responses: List[Tuple[str, str, int]],
        total_metrics: Dict[str, float],
        n_iterations: int
    ):
        print("Initial round responses:")
        print("-"*40)
        debate_input = requirement
        for idx, (assistant_name, model) in enumerate(assistants):
            thread_id = assistant_threads[assistant_name]


            if (idx > 0):
                debate_input = requirement + "\n\nOpossing arguments:\n\n"
                for name,resp,round in responses:
                    debate_input += "Assistant" + name +" response:\n" + resp

            # print(f"Input Assistant {assistant_name} with input:\n{debate_input}\n")
            print("*"*40)
            print(f"\nInput to Assistant '{assistant_name}' [Thread ID: {thread_id}]:")
            print(f"{debate_input}")
            print("\nResponse:")
            result_assistant_name, result_response, result_number_iteration = self.assistant_response(
                thread_id,
                debate_input,
                assistant_name,
                model,
                temperature,
                total_metrics,
                0,
            )
            # print(f"Output {result_response}\n")

            responses.append((result_assistant_name, result_response, result_number_iteration))

        current_responses = [(name, resp) for name, resp, _ in responses]

        for iteration in range(n_iterations):
            print(f"\nIteration {iteration + 1} responses:")
            print("-"*40)
            new_responses = []
            for idx, (assistant_name, model) in enumerate(assistants):
                thread_id = assistant_threads[assistant_name]
                # Get the most recent responses from other assistants
                other_responses = "\n\n".join([
                    f"Assistant '{name}' response:\n{resp}"
                    for name, resp in current_responses if name != assistant_name
                ])

                # For subsequent iterations, only provide opposing arguments
                debate_input = f"Opposing arguments:\n\n{other_responses}"

                # print(f"\nInput Assistant {assistant_name} with input:\n{debate_input}\n")
                print("*"*40)
                print(f"\nInput to Assistant '{assistant_name}' [Thread ID: {thread_id}]:")
                print(f"{debate_input}")
                print("\nResponse:")


                result_assistant_name, result_response, result_number_iteration = self.assistant_response(
                    thread_id,
                    debate_input,
                    assistant_name,
                    model,
                    temperature,
                    total_metrics,
                    iteration + 1
                )
                responses.append((result_assistant_name, result_response, result_number_iteration))
                new_responses.append((result_assistant_name, result_response, result_number_iteration))
                current_responses.pop(0) # This is done to avoid sending a response from the previous iteration. Without this you receive the previous response of an assistant and also the even more previous response. However the even more previous response was already given as input in the previous iteration. that's why this operation is necessary.
                current_responses.append((result_assistant_name, result_response))

                # print(f"Output {result_response}")


            current_responses = new_responses

    def assistant_response(
        self,
        thread_id: int,
        requirement: str,
        assistant_name: str,
        model: str,
        temperature: float,
        total_metrics: Dict[str, float],
        number_iteration: int,
    ) -> Tuple[str, str, int]:
            
        # Add retry logic for initial responses
        while True:
            response, metrics = self.caller.send_message(
                requirement,
                assistant_name=assistant_name,
                model=model,
                temperature=temperature,
                thread_id=thread_id
            )
            if "Run status: failed" not in response and "Run status: expired" not in response:
                break
            print(f"Retrying failed/expired message for {assistant_name}...")
        
        print(f"{response}")    
        for key in total_metrics:
            if key != 'execution_time':
                total_metrics[key] += metrics[key]

        return (assistant_name, response, number_iteration)


class LLMCoordinator:
    def __init__(self, api_key: str, protocol_type: str):
        """Initialize the coordinator with an API key."""
        self.caller = OpenAIAssistantCaller(api_key=api_key)
        self.protocol = InteractionProtocol(self.caller, protocol_type)
    
    def judge_approach(
        self,
        requirement: str,
        assistants: List[Tuple[str, str]],
        judge: Tuple[str, str],
        temperature: float = 0,
        n_iterations: int = 0
    ) -> Tuple[Dict, Dict, List]:
        responses = []
        """Process a single requirement through assistants and judge."""
        start_time = time.time()
        total_metrics = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'execution_time': 0
        }

        print("\n" + "="*80)

        # Create a thread for each assistant for this requirement
        assistant_threads = {
            assistant_name: self.caller.create_thread()
            for assistant_name, _ in assistants
        }

        self.protocol.run(
            assistants,
            assistant_threads,
            requirement,
            temperature,
            responses,
            total_metrics,
            n_iterations,
        )
        # Clean up threads
        #for thread_id in assistant_threads.values():
        #    self.caller.delete_thread(thread_id)

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
            
            # Add retry logic for judge responses
            while True:
                raw_decision, metrics = self.caller.send_message(
                    judge_input,
                    assistant_name=judge_name,
                    model=judge_model,
                    temperature=temperature
                )
                if "Run status: failed" not in raw_decision and "Run status: expired" not in raw_decision:
                    break
                print(f"Retrying failed/expired message for judge...")

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
        return decisions, total_metrics, responses

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
        
        # Create output files for each iteration
        output_files = {}
        metrics_files = {}
        for n in range(n_iterations + 1):
            # Create output file names with iteration number
            base_name = output_file.stem
            output_path = output_file.parent / f"{base_name}_n{n}{output_file.suffix}"
            metrics_path = output_file.parent / f"{base_name}_metrics_n{n}.json"
            
            # Create columns for each assistant's response at each iteration
            df_with_responses = df.copy()
            for iteration in range(n + 1):  # Only include columns up to current iteration
                for assistant_name, _ in assistants:
                    col_name = f"response_{assistant_name}_iter{iteration}"
                    df_with_responses[col_name] = ''
            df_with_responses['judge'] = ''
            
            # Initialize files
            df_with_responses.head(0).to_csv(output_path, index=False)
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
                decisions, metrics, responses = self.judge_approach(
                    requirement,
                    assistants,
                    judge,
                    temperature,
                    n_iterations
                )
                
                # Save results for each iteration
                for n in range(n_iterations + 1):
                    row_copy = row.copy()
                    
                    # Add responses up to current iteration
                    for iteration in range(n + 1):
                        for assistant_name, _ in assistants:
                            col_name = f"response_{assistant_name}_iter{iteration}"
                            # Find the response for this assistant at this iteration
                            response = next(
                                (response for name, response, round_num in responses 
                                 if name == assistant_name and round_num == iteration),
                                ''  # Default value if not found
                            )
                            row_copy[col_name] = response
                    
                    row_copy['judge'] = decisions[n]
                    pd.DataFrame([row_copy]).to_csv(output_files[n], mode='a', header=False, index=False)
                    
                    # Update metrics file
                    with open(metrics_files[n], 'r') as f:
                        current_metrics = json.load(f)
                    
                    # Calculate execution time up to this iteration
                    iteration_time = metrics['execution_time'] * (n + 1) / (n_iterations + 1)
                    
                    # Update metrics
                    for key in metrics:
                        if key == 'execution_time':
                            current_metrics[key] += iteration_time
                        else:
                            current_metrics[key] += metrics[key] * (n + 1) / (n_iterations + 1)
                    
                    current_metrics['requirements_processed'] += 1
                    
                    with open(metrics_files[n], 'w') as f:
                        json.dump(current_metrics, f)

            except Exception as e:
                print(f"Error processing requirement {idx}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Process requirements through assistants and judge')
    parser.add_argument('--input', type=Path, required=True, help='Input CSV file path')
    parser.add_argument('--output', type=Path, required=True, help='Output CSV file path')
    parser.add_argument('--assistants-file', type=Path, required=True, help='JSON file with assistant configs')
    parser.add_argument('--judge-file', type=Path, required=True, help='JSON file with judge config')
    parser.add_argument('--temperature', type=float, default=0, help='Temperature for generation')
    parser.add_argument('--n', type=int, help='Number of requirements to sample per class (optional)')
    parser.add_argument('--iterations', type=int, default=0, help='Number of debate iterations')
    parser.add_argument('--protocol_type', type=str, choices = InteractionProtocol.STRATEGIES.keys(), default="simultaneous", help='Choose Interaction Protocol: "simultaneous" , "sequential"')
    args = parser.parse_args()

    print("The debate will be done by " + args.protocol_type + " protocol debate")

    # Initialize coordinator
    coordinator = LLMCoordinator(api_key=os.getenv("OPENAI_API_KEY"), protocol_type = args.protocol_type)

    # Load configurations
    with open(args.assistants_file) as f:
        assistants = json.load(f)  # Expected: [["assistant1_name", "model1"], ...]
    with open(args.judge_file) as f:
        judge = json.load(f)  # Expected: ["judge_name", "model"]

    # Protocol Strategy
    # protocol_class = PROTOCOL_REGISTRY[args.protocol]

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
