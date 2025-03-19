import os
import argparse
from openai import OpenAI
from typing import Dict, Any
from dotenv import load_dotenv
from ..create_assistant import AssistantCreator

class OpenAIAssistantCreator(AssistantCreator):
    def _initialize_client(self) -> OpenAI:
        return OpenAI(api_key=self.api_key)
    
    def get_json_schema(self) -> Dict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "placeholder_schema",
                "description": "A placeholder JSON schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "result": {
                            "type": "string"
                        }
                    },
                    "required": ["result"]
                }
            }
        }
    
    def create_assistant(self, model: str = "gpt-4o", temperature: float = 0.0) -> Any:
        instructions = self.get_base_instructions()
        
        print("Creating a new OpenAI assistant...")
        
        assistant = self.client.beta.assistants.create(
            name=self.assistant_name,
            instructions=instructions,
            model=model,
            temperature=temperature,
            response_format=self.get_json_schema()
        )
        
        self.save_assistant_id(assistant.id, model)
        print(f"Assistant created successfully. Assistant ID: {assistant.id}")
        return assistant

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Create an OpenAI assistant for a particular task.')
    parser.add_argument('--model', default="gpt-4o", help='OpenAI model to use')
    parser.add_argument('--assistant_name', default="placeholder_assistant", help='Name of the assistant')
    parser.add_argument('--temperature', type=float, default=0.0, help='Temperature parameter for the model (0.0 to 2.0)')
    parser.add_argument('--prompt_file_path', default="data/prompts/system-prompt.txt", help='Path to the prompt file')
    
    args = parser.parse_args()
    
    creator = OpenAIAssistantCreator(api_key=os.getenv("OPENAI_API_KEY"), assistant_name=args.assistant_name, prompt_file_path=args.prompt_file_path)
    creator.create_assistant(model=args.model, temperature=args.temperature)

if __name__ == "__main__":
    main() 