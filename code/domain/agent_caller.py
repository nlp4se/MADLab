from datetime import datetime
from typing import Dict, Tuple

from .contracts.external_agent_caller import ExternalAgentCaller
from .contracts.agent_record import AgentRecord


class AgentCaller:
    def __init__(self, external_caller: ExternalAgentCaller, agent_record: AgentRecord):
        self.external_caller = external_caller
        self.agent_record = agent_record

    def start_session(self) -> str:
        return self.external_caller.start_session()

    def submit_message(self, message: str, assistant_name: str, **kwargs) -> Tuple[str, Dict]:
        assistant_id = self.agent_record.get_id(assistant_name)
        session_id = kwargs.pop('session_id', None) or kwargs.pop('thread_id', None)
        if session_id is None:
            session_id = self.start_session()
        return self.external_caller.send_message(message, assistant_id, session_id, **kwargs)

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
