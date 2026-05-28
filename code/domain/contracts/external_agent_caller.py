from abc import ABC, abstractmethod
from typing import Dict, Tuple


class ExternalAgentCaller(ABC):
    @abstractmethod
    def start_session(self) -> str:
        pass

    @abstractmethod
    def send_message(self, message: str, assistant_id: str, session_id: str, **kwargs) -> Tuple[str, Dict]:
        pass
