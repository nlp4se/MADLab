from typing import List, Dict, Tuple, Any
import pandas as pd
from pathlib import Path
import json
from tqdm import tqdm
import time
from pubsub import pub

from .agent_caller import AgentCaller


class DebaterAgent:
    def __init__(self, name: str, session_id: str, caller: AgentCaller, temperature: float, channels_to_listen: List[str]):
        self.name = name
        self.session_id = session_id
        self.caller = caller
        self.temperature = temperature

        self.inbox = []
        self.response_ready_to_send = None

        # --- SUBSCRIPTIONS TO DATA BUS ---
        for channel in channels_to_listen:
            pub.subscribe(self.receive_data, channel)
        pub.subscribe(self.receive_data, "requirement_channel")

        # --- SUBSCRIPTIONS TO CONTROL BUS ---
        pub.subscribe(self.process_and_clear, f"process_{self.name}")
        pub.subscribe(self.send_response, f"send_{self.name}")

    def receive_data(self, sender: str, content: str, round_number: int = None):  # The round number is required to match send_response's signature. The DebaterAgent doesn't need it, but the JudgeAgent listening on this same channel does.
        self.inbox.append((sender, content))

    def process_and_clear(self, round_number: int):
        data_to_process = list(self.inbox)
        self.inbox.clear()

        # 1. Build the prompt based on received data
        debate_input = self.build_debate_input(round_number, data_to_process)

        print(f"\n    Input to Assistant '{self.name}' [Session ID: {self.session_id}]:")
        print(f"      {debate_input.replace(chr(10), chr(10) + '      ')}")
        print("\n    Response:")

        # 2. Call the LLM via the core AgentCaller
        response, metrics = self._call_api(debate_input)

        print(f"      {response.replace(chr(10), chr(10) + '      ')}")

        # Save the response and send metrics to monitor
        self.response_ready_to_send = response
        pub.sendMessage("metrics_channel", metrics=metrics)

    def build_debate_input(self, round_number, data_to_process):
        requirement_base = ""
        opposing_args = []

        for sender, content in data_to_process:
            if sender == "Coordinator":
                requirement_base = content
            else:
                opposing_args.append(f"Assistant '{sender}' response:\n{content}")

        debate_input_parts = []

        if round_number == 0 and requirement_base:
            debate_input_parts.append(requirement_base)

        if opposing_args:
            debate_input_parts.append("Opposing arguments:\n" + "\n\n".join(opposing_args))
        return "\n\n".join(debate_input_parts)

    def _call_api(self, debate_input: str) -> tuple:
        while True:
            response, metrics = self.caller.submit_message(
                debate_input,
                assistant_name=self.name,
                temperature=self.temperature,
                session_id=self.session_id
            )
            if "Run status: failed" not in response and "Run status: expired" not in response:
                return response, metrics

    def send_response(self, round_number: int):
        if self.response_ready_to_send:
            pub.sendMessage(self.name, sender=self.name, content=self.response_ready_to_send, round_number=round_number)   # We send round_number strictly so the listening JudgeAgent can track the debate turns.
            self.response_ready_to_send = None


class JudgeAgent:
    def __init__(self, name: str, channels_to_listen: List[str], caller: AgentCaller, session_id: str, temperature: float = 0):
        self.name = name
        self.responses = []
        self.total_metrics = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'execution_time': 0
        }
        self.caller = caller
        self.temperature = temperature
        self.session_id = session_id

        for channel in channels_to_listen:
            pub.subscribe(self.register_response, channel)

        pub.subscribe(self.register_metrics, "metrics_channel")

    def _call_api(self, judge_input: str) -> tuple:
        while True:
            response, metrics = self.caller.submit_message(
                judge_input,
                assistant_name=self.name,
                temperature=self.temperature,
                session_id=self.session_id
            )
            if "Run status: failed" not in response and "Run status: expired" not in response:
                return response, metrics
            print(f"Retrying failed/expired message for judge...")

    def register_response(self, sender: str, content: str, round_number: int):
        self.responses.append((sender, content, round_number))

    def register_metrics(self, metrics: Dict[str, float]):
        for key in self.total_metrics:
            if key != 'execution_time' and key in metrics:
                self.total_metrics[key] += metrics[key]


class MadDebate:
    def __init__(self, caller: AgentCaller):
        """Initialize the debate orchestrator with an AgentCaller instance."""
        self.caller = caller

    def run_debate(
        self,
        requirement: str,
        assistants: List[str],
        topology: Dict[str, List[str]],
        turns: Any,
        judge: str,
        temperature: float = 0,
        n_iterations: int = 0
    ) -> Tuple[List, Dict]:
        """Execute the debate between assistants and return responses and metrics."""
        # Clear previous subscriptions and instantiate Judge Node to collect all debate responses and metrics
        pub.unsubAll()
        self.judge = JudgeAgent(
            name=judge,
            channels_to_listen=assistants,
            caller=self.caller,
            temperature=temperature,
            session_id=self.caller.start_session()
        )

        # Create sessions (one persistent conversation per debater)
        assistant_sessions = {
            name: self.caller.start_session() for name in assistants
        }

        # Instantiate agents iterating over the graph configuration provided in interaction_file JSON
        instantiated_nodes = {}
        for name in assistants:
            edges = topology.get(name, [])
            instantiated_nodes[name] = DebaterAgent(
                name=name,
                session_id=assistant_sessions[name],
                caller=self.caller,
                temperature=temperature,
                channels_to_listen=edges
            )

        # ==========================================
        # ORCHESTRATOR EXECUTION
        # ==========================================

        # The coordinator launches the requirement to classify
        pub.sendMessage("requirement_channel", sender="Coordinator", content=requirement)

        for round_num in range(n_iterations + 1):
            print(f"\nRound {round_num}")

            current_round_turns = turns if not isinstance(turns, dict) else turns.get(str(round_num), [])

            for turn_number, node_group in enumerate(current_round_turns, 0):
                print(f"\n  Turn {turn_number} {node_group}:")

                # Step 1: Tell agents in this turn to process their inbox
                for node_name in node_group:
                    pub.sendMessage(f"process_{node_name}", round_number=round_num)

                # Step 2: Once all agents have processed their inbox, tell them to emit their responses. It is necessary to have this as a separate step to ensure that all agents in the same turn are responding based on the current information (the state of the debate at the beginning of the turn), and not reacting to each other's responses within the same turn.
                for node_name in node_group:
                    pub.sendMessage(f"send_{node_name}", round_number=round_num)

        # Debate finished, retrieve history
        responses = self.judge.responses
        metrics = self.judge.total_metrics

        return responses, metrics

    def judge_approach(
        self,
        requirement: str,
        responses: List,
        metrics: Dict,
        temperature: float = 0,
        n_iterations: int = 0
    ) -> Tuple[Dict, Dict, List]:
        """Analyze debate results using the judge and return decisions, metrics, and responses."""

        decisions = {}
        judge_metrics = {}

        print("\nJudge decisions:")
        print("-"*40)
        for n in range(n_iterations + 1):
            filtered_responses = [r for r in responses if r[2] <= n]
            discussion_history = "\n\n".join([
                f"Round {round_num} - Assistant '{name}' response:\n{response}"
                for name, response, round_num in filtered_responses
            ])

            judge_input = f"Requirement: {requirement}\n\n{discussion_history}"

            raw_decision, judge_metrics_iter = self.judge._call_api(judge_input)

            try:
                decision_obj = json.loads(raw_decision)
                decisions[n] = decision_obj['class']
                judge_metrics[n] = judge_metrics_iter
                print(f"\nFor iteration {n}:")
                print(f"Decision: {decision_obj['class']}")
                print(f"Raw response: {raw_decision}")

                for key in metrics:
                    if key != 'execution_time':
                        metrics[key] += judge_metrics_iter[key]
            except (json.JSONDecodeError, KeyError) as e:
                raise Exception(f"Invalid judge response format: {raw_decision}") from e

        return decisions, metrics, responses

    def process_dataset(
        self,
        input_file: Path,
        output_file: Path,
        assistants: List[str],
        topology: Dict[str, List[str]],
        turns: Any,
        judge: str,
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
                for assistant_name in assistants:
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
                start_time = time.time()
                print("\n" + "="*80)

                # Run the debate
                responses, metrics = self.run_debate(
                    requirement,
                    assistants,
                    topology,
                    turns,
                    judge,
                    temperature,
                    n_iterations
                )

                # Analyze debate results with judge
                decisions, metrics, responses = self.judge_approach(
                    requirement,
                    responses,
                    metrics,
                    temperature,
                    n_iterations
                )

                metrics['execution_time'] = time.time() - start_time
                print("\n" + "="*80)

                # Save results for each iteration
                for n in range(n_iterations + 1):
                    row_copy = row.copy()

                    # Add responses up to current iteration
                    for iteration in range(n + 1):
                        for assistant_name in assistants:
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
