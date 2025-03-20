from typing import List, Tuple, Dict
import argparse
import os
from dotenv import load_dotenv
import json

from .openai.ask_assistant_openai import OpenAIAssistantCaller

load_dotenv()

class LLMCoordinator:
    def __init__(self, api_key: str):
        """Initialize the coordinator with an API key."""
        self.caller = OpenAIAssistantCaller(api_key=api_key)

    def summarization_approach(
        self, 
        # change message to file path
        message: str, 
        assistants: List[Tuple[str, str]], 
        coordinator: Tuple[str, str],
        coordinator_prompt_file: str,
        temperature: float = 0
    ) -> Dict:
        """
        Coordinate discussion using the summarization approach.
        
        Args:
            message: The user's prompt
            assistants: List of (assistant_name, model) pairs to get responses from
            coordinator: Tuple of (assistant_name, model) for the summarizing assistant
            coordinator_prompt_file: Path to the file containing the coordinator prompt template
            temperature: Temperature parameter for generation
            
        Returns:
            Dictionary containing responses and metrics
        """
        # Store all responses and accumulate metrics
        responses = []
        total_metrics = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        }

        # Get responses from all assistants
        for assistant_name, model in assistants:
            response, metrics = self.caller.send_message(
                message,
                assistant_name=assistant_name,
                model=model,
                temperature=temperature
            )
            responses.append((assistant_name, response))
            
            # Accumulate metrics
            for key in total_metrics:
                total_metrics[key] += metrics[key]

        # Load the coordinator prompt template
        try:
            with open(coordinator_prompt_file, 'r') as file:
                summary_prompt_template = file.read().strip()
        except FileNotFoundError:
            print(f"Error: Coordinator prompt file '{coordinator_prompt_file}' not found.")
            raise

        # Build the assistant responses section
        assistant_responses_text = ""
        for assistant_name, response in responses:
            assistant_responses_text += f"Assistant '{assistant_name}' responded:\n{response}\n\n"

        # Construct the final prompt by replacing the placeholder
        summary_prompt = summary_prompt_template.format(
            assistant_responses=assistant_responses_text.strip()
        )

        # Get the final summarized response
        coordinator_name, coordinator_model = coordinator
        final_response, summary_metrics = self.caller.send_message(
            summary_prompt,
            assistant_name=coordinator_name,
            model=coordinator_model,
            temperature=temperature
        )

        # Add coordinator metrics to total
        for key in total_metrics:
            total_metrics[key] += summary_metrics[key]

        return {
            'individual_responses': responses,
            'final_response': final_response,
            'metrics': total_metrics
        }

    def coordinate(
        self, 
        approach: str,
        message: str,
        **kwargs
    ) -> Dict:
        """
        Main coordination method that handles different approaches.
        
        Args:
            approach: The coordination approach to use (e.g., 'summarization')
            message: The user's prompt
            **kwargs: Additional arguments specific to each approach
            
        Returns:
            Dictionary containing the response and metrics
        """
        if approach == "summarization":
            required_args = ['assistants', 'coordinator', 'coordinator_prompt_file']
            if not all(arg in kwargs for arg in required_args):
                raise ValueError(f"Summarization approach requires: {required_args}")
            
            return self.summarization_approach(
                message,
                kwargs['assistants'],
                kwargs['coordinator'],
                kwargs['coordinator_prompt_file'],
                kwargs.get('temperature', 0)
            )
        else:
            raise ValueError(f"Unknown approach: {approach}")

def main():

    parser = argparse.ArgumentParser(description='Coordinate LLM discussions using different approaches.')
    parser.add_argument('--approach', 
                       default='summarization',
                       help='Coordination approach to use (e.g., summarization)')
    parser.add_argument('--assistants_file',
                       default='data/config/assistants.json',
                       help='JSON file containing list of assistant-model pairs')
    parser.add_argument('--coordinator_file',
                       default='data/config/coordinator.json',
                       help='JSON file containing coordinator assistant-model pair')
    parser.add_argument('--discussant_prompt_file',
                       default='data/prompts/discussant/user-prompt.txt',
                       help='Path to the file containing the discussion prompt')
    parser.add_argument('--coordinator_prompt_file',
                       default='data/prompts/coordinator/user-prompt.txt',
                       help='Path to the file containing the coordinator prompt template')
    parser.add_argument('--temperature',
                       type=float,
                       default=0,
                       help='Temperature for generation')

    args = parser.parse_args()

    # Read prompt from file
    try:
        with open(args.discussant_prompt_file, 'r') as file:
            message = file.read().strip()
    except FileNotFoundError:
        print(f"Error: Prompt file '{args.prompt_file}' not found.")
        return
    
    # Read assistants configuration
    try:
        with open(args.assistants_file, 'r') as file:
            assistants = json.load(file)
            # Expected format: [["assistant1_name", "model1"], ["assistant2_name", "model2"]]
    except FileNotFoundError:
        print(f"Error: Assistants configuration file '{args.assistants_file}' not found.")
        return

    # Read coordinator configuration
    try:
        with open(args.coordinator_file, 'r') as file:
            coordinator = json.load(file)
            # Expected format: ["coordinator_name", "model"]
    except FileNotFoundError:
        print(f"Error: Coordinator configuration file '{args.coordinator_file}' not found.")
        return

    # Initialize coordinator
    coordinator_instance = LLMCoordinator(api_key=os.getenv("OPENAI_API_KEY"))

    # Get coordinated response
    result = coordinator_instance.coordinate(
        approach=args.approach,
        message=message,
        assistants=assistants,
        coordinator=coordinator,
        coordinator_prompt_file=args.coordinator_prompt_file,
        temperature=args.temperature
    )

    # Print results
    print("\nIndividual Responses:")
    for assistant_name, response in result['individual_responses']:
        print(f"\n{assistant_name}:")
        print(response)

    print("\nFinal Synthesized Response:")
    print(result['final_response'])

    print("\nToken Usage Metrics:")
    print(json.dumps(result['metrics'], indent=2))

if __name__ == "__main__":
    main()
