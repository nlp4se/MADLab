from openai import OpenAI
import json
import os
import time
from typing import Any, Dict, Tuple
from dotenv import load_dotenv
from ..ask_assistant import AssistantCaller
import argparse

class OpenAIAssistantCaller(AssistantCaller):
    def _initialize_client(self) -> OpenAI:
        return OpenAI(api_key=self.api_key)

    def create_thread(self) -> str:
        """Create a new thread for conversation persistence."""
        return self.client.beta.threads.create().id

    def get_assistant_id(self, model: str, assistant_name: str) -> str:
        """Load assistant ID from file."""
        filename = f"data/assistants/assistant_{assistant_name}_{model}.txt"
        with open(filename, 'r') as file:
            return file.read().strip()

    def send_message(self, message: str, **kwargs) -> Tuple[str, Dict]:
        """Send a message to the assistant and get the response.
        
        Args:
            message: The message to send to the assistant
            **kwargs: Additional arguments including assistant_name and model
            
        Returns:
            Tuple containing:
            - Assistant's response as a string
            - Dictionary with token usage information
        """
        assistant_name = kwargs.get('assistant_name', 'placeholder_assistant')
        model = kwargs.get('model', 'gpt-4')
        temperature = kwargs.get('temperature', 0)
        
        assistant_id = self.get_assistant_id(model, assistant_name)
        thread_id = self.create_thread()

        try:
            # Create message in thread
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message
            )

            # Create and monitor run
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id,
                temperature=temperature
            )

            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id, 
                    run_id=run.id
                )
                if run_status.status == "completed":
                    break
                elif run_status.status not in ["in_progress", "queued"]:
                    print(f"Run status: {run_status.status}")
                time.sleep(2)

            # Get response
            messages = self.client.beta.threads.messages.list(thread_id=thread_id)
            response = messages.data[0].content[0].text.value

            # Collect usage statistics
            usage_metadata = {
                'prompt_tokens': getattr(run_status.usage, "prompt_tokens", 0),
                'completion_tokens': getattr(run_status.usage, "completion_tokens", 0),
                'total_tokens': getattr(run_status.usage, "total_tokens", 0)
            }

            return response, usage_metadata

        except Exception as e:
            print(f"Error processing message: {e}")
            return "", {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Send a message to an OpenAI assistant.')
    parser.add_argument('--assistant_name', 
                       default='placeholder_assistant',
                       help='Name of the assistant to use')
    parser.add_argument('--model', 
                       default='gpt-4o',
                       help='Model to use (e.g., gpt-4o)')
    parser.add_argument('--prompt_file',
                        default='data/prompts/discussant/user-prompt.txt',
                       help='Path to the file containing the prompt')
    
    args = parser.parse_args()
    
    # Read prompt from file
    try:
        with open(args.prompt_file, 'r') as file:
            message = file.read().strip()
    except FileNotFoundError:
        print(f"Error: Prompt file '{args.prompt_file}' not found.")
        return
    except Exception as e:
        print(f"Error reading prompt file: {e}")
        return
    
    # Initialize the caller
    caller = OpenAIAssistantCaller(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Process the message and get metrics
    metrics = caller.process_with_metrics(
        message,
        assistant_name=args.assistant_name,
        model=args.model
    )
    
    # Print the response
    if metrics['success']:
        print("\nAssistant's response:")
        print(metrics['response'])
    else:
        print("\nError:", metrics['error'])

if __name__ == "__main__":
    main() 