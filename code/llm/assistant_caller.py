from abc import ABC, abstractmethod
import time
from datetime import datetime
from typing import Any, Dict, Tuple

from ..persistence.assistant_file import AssistantFile


class AssistantCaller(ABC):
    def __init__(self, api_key: str, assistant_file: AssistantFile):
        self.api_key = api_key
        self.assistant_file = assistant_file
        self.client = self._initialize_client()

    @abstractmethod
    def _initialize_client(self) -> Any:
        pass

    def submit_message(self, message: str, assistant_name: str, **kwargs) -> Tuple[str, Dict]:
        assistant_id = self.assistant_file.get_assistant_record_id(assistant_name)
        return self.send_message(message, assistant_id, **kwargs)

    @abstractmethod
    def send_message(self, message: str, assistant_id: str, **kwargs) -> Tuple[str, Dict]:
        pass

    def process_with_metrics(self, message: str, assistant_name: str, **kwargs) -> Dict:
        start_time = datetime.now()
        print(f"Starting processing at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        metrics = {
            'start_time': start_time.isoformat(),
            'total_tokens': 0,
            'total_prompt_tokens': 0,
            'total_completion_tokens': 0
        }

        try:
            response, usage_metadata = self.submit_message(message, assistant_name, **kwargs)
            metrics.update({
                'total_tokens': usage_metadata.get('total_tokens', 0),
                'total_prompt_tokens': usage_metadata.get('prompt_tokens', 0),
                'total_completion_tokens': usage_metadata.get('completion_tokens', 0),
                'success': True,
                'response': response
            })
        except Exception as e:
            metrics.update({
                'success': False,
                'error': str(e)
            })

        end_time = datetime.now()
        metrics.update({
            'end_time': end_time.isoformat(),
            'total_duration': (end_time - start_time).total_seconds()
        })

        print(f"Processing completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')} "
              f"(Duration: {metrics['total_duration']:.2f}s)")
        print(f"Total tokens used: {metrics['total_tokens']}")

        return metrics
