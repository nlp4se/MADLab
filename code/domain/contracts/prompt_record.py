from abc import ABC, abstractmethod


class PromptRecord(ABC):
    @abstractmethod
    def get(self, prompt_path: str) -> str:
        pass

    @abstractmethod
    def create(self, prompt_path: str, content: str) -> None:
        pass

    @abstractmethod
    def update(self, prompt_path: str, content: str) -> None:
        pass

    @abstractmethod
    def delete(self, prompt_path: str) -> bool:
        pass
