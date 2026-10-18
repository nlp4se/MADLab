import os
import json
import uuid
from typing import Dict, List, Tuple

from openai import OpenAI, NOT_GIVEN

from ...domain.contracts.external_agent_caller import ExternalAgentCaller
from ...domain.contracts.agent_record import AgentDefinition


class OpenAIAgentCaller(ExternalAgentCaller):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)
        # Full conversation history of each session, kept in memory. OpenAI stores nothing (store=False)
        self.sessions: Dict[str, List[Dict]] = {}

    def _get_text_format(self, schema_file_path: str = None):
        if schema_file_path and os.path.exists(schema_file_path):
            with open(schema_file_path, 'r', encoding='utf-8') as f:
                return {"format": {"type": "json_schema", **json.load(f)}}
        return NOT_GIVEN

    def start_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = []
        return session_id

    def send_message(self, message: str, agent: AgentDefinition, session_id: str, **kwargs) -> Tuple[str, Dict]:
        temperature = kwargs.get('temperature', agent.temperature)
        history = self.sessions.setdefault(session_id, [])
        history.append({"role": "user", "content": message})

        try:
            response = self.client.responses.create(
                model=agent.model,
                instructions=agent.instructions,
                input=history,
                temperature=temperature,
                text=self._get_text_format(agent.schema_file_path),
                store=False,
            )
        except Exception as e:
            history.pop()  # Drop the unanswered message so a retry does not duplicate it
            print(f"Error processing message: {e}")
            return f"Run status: failed - {str(e)}", {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            }

        history.append({"role": "assistant", "content": response.output_text})

        usage_metadata = {
            'prompt_tokens': response.usage.input_tokens,
            'completion_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.total_tokens
        }

        return response.output_text, usage_metadata
