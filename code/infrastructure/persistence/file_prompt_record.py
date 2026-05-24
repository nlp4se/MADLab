import os

from ...core.ports.prompt_record import PromptRecord


class FilePromptRecord(PromptRecord):
    def __init__(self, base_dir: str = "data/prompts"):
        self.base_dir = base_dir

    def _path(self, prompt_path: str) -> str:
        return os.path.join(self.base_dir, prompt_path)

    def get(self, prompt_path: str) -> str:
        full_path = self._path(prompt_path)
        try:
            with open(full_path, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Prompt file not found: '{full_path}'"
            )
        if not content.strip():
            raise ValueError(
                f"Prompt file is empty: '{full_path}'"
            )
        return content

    def create(self, prompt_path: str, content: str) -> None:
        full_path = self._path(prompt_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"PromptRecord created at '{full_path}'")

    def update(self, prompt_path: str, content: str) -> None:
        full_path = self._path(prompt_path)
        if not os.path.exists(full_path):
            raise FileNotFoundError(
                f"Prompt file not found: '{full_path}'"
            )
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"PromptRecord updated at '{full_path}'")

    def delete(self, prompt_path: str) -> bool:
        full_path = self._path(prompt_path)
        if not os.path.exists(full_path):
            print(f"PromptRecord did not exist: '{full_path}'")
            return False
        os.remove(full_path)
        print(f"PromptRecord deleted: '{full_path}'")
        return True
