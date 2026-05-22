import time
from openai import OpenAI, NotFoundError
from typing import Any, Dict, Tuple

from ..assistant_caller import AssistantCaller
from ...persistence.assistant_file import AssistantFile


class OpenAIAssistantCaller(AssistantCaller):
    def _initialize_client(self) -> OpenAI:
        return OpenAI(api_key=self.api_key)

    def create_thread(self) -> str:
        return self.client.beta.threads.create().id

    def send_message(self, message: str, assistant_id: str, **kwargs) -> Tuple[str, Dict]:
        temperature = kwargs.get('temperature', 0)
        thread_id = kwargs.get('thread_id', self.create_thread())

        try:
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message
            )

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
                    return f"Run status: {run_status.status}", {
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0
                    }
                time.sleep(2)

            messages = self.client.beta.threads.messages.list(thread_id=thread_id)
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
                f"Remove the corresponding assistant file and recreate the assistant."
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
