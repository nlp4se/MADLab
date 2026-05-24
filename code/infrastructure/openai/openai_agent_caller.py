import time
from openai import OpenAI, NotFoundError
from typing import Dict, Tuple

from ...core.ports.external_agent_caller import ExternalAgentCaller


class OpenAIAgentCaller(ExternalAgentCaller):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

    def start_session(self) -> str:
        return self.client.beta.threads.create().id

    def send_message(self, message: str, assistant_id: str, session_id: str, **kwargs) -> Tuple[str, Dict]:
        temperature = kwargs.get('temperature', 0)

        try:
            self.client.beta.threads.messages.create(
                thread_id=session_id,
                role="user",
                content=message
            )

            run = self.client.beta.threads.runs.create(
                thread_id=session_id,
                assistant_id=assistant_id,
                temperature=temperature
            )

            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=session_id,
                    run_id=run.id
                )
                if run_status.status == "completed":
                    break
                elif run_status.status not in ["in_progress", "queued"]:
                    print(f"Run status: {run_status.status}")
                    return f"Run status: {run_status.status}", {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    }
                time.sleep(2)

            messages = self.client.beta.threads.messages.list(thread_id=session_id)
            response = messages.data[0].content[0].text.value

            usage_metadata = {
                'prompt_tokens': getattr(run_status.usage, "prompt_tokens", 0),
                'completion_tokens': getattr(run_status.usage, "completion_tokens", 0),
                'total_tokens': getattr(run_status.usage, "total_tokens", 0)
            }

            return response, usage_metadata

        except NotFoundError:
            error_msg = (
                f"Assistant with ID '{assistant_id}' not found in OpenAI. "
                f"It may have been deleted externally. "
                f"Remove the corresponding AgentRecord and recreate the assistant."
            )
            print(f"Error: {error_msg}")
            return f"Run status: failed - {error_msg}", {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            }
        except Exception as e:
            print(f"Error processing message: {e}")
            return f"Run status: failed - {str(e)}", {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            }
