from abc import ABC, abstractmethod
import json
import time
from datetime import datetime
from typing import Any, Dict, Tuple

class AssistantCaller(ABC):
    """Abstract base class for making calls to AI assistants."""
    
    def __init__(self, api_key: str):
        """Initialize with API key and client."""
        self.api_key = api_key
        self.client = self._initialize_client()

    @abstractmethod
    def _initialize_client(self) -> Any:
        """Initialize the specific AI provider's client."""
        pass

    @abstractmethod
    def send_message(self, message: str, **kwargs) -> Tuple[str, Dict]:
        """Send a message to the assistant and get the response.
        
        Args:
            message: The message to send to the assistant
            **kwargs: Additional arguments for the specific implementation
            
        Returns:
            Tuple containing:
            - Assistant's response as a string
            - Dictionary with token usage information
        """
        pass

    def process_with_metrics(self, message: str, **kwargs) -> Dict:
        """Send a message and track metrics."""
        start_time = datetime.now()
        print(f"Starting processing at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        metrics = {
            'start_time': start_time.isoformat(),
            'total_tokens': 0,
            'total_prompt_tokens': 0,
            'total_completion_tokens': 0
        }

        try:
            # Process the message
            response, usage_metadata = self.send_message(message, **kwargs)

            # Update metrics
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

        # Record final timing metrics
        end_time = datetime.now()
        metrics.update({
            'end_time': end_time.isoformat(),
            'total_duration': (end_time - start_time).total_seconds()
        })

        # Print summary
        print(f"Processing completed at {end_time.strftime('%Y-%m-%d %H:%M:%S')} "
              f"(Duration: {metrics['total_duration']:.2f}s)")
        print(f"Total tokens used: {metrics['total_tokens']}")

        return metrics 