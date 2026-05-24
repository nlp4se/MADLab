import os

from ...core.ports.agent_record import AgentRecord


class FileAgentRecord(AgentRecord):
    def __init__(self, base_dir: str = "data/assistant_records"):
        self.base_dir = base_dir

    def _path(self, name: str) -> str:
        return os.path.join(self.base_dir, f"assistant_{name}.txt")

    def get_id(self, name: str) -> str:
        path = self._path(name)
        try:
            with open(path, 'r') as f:
                assistant_id = f.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"No AgentRecord found for '{name}'. "
                f"Make sure the OpenAI Assistant has been created and registered first."
            )
        if not assistant_id:
            raise ValueError(
                f"AgentRecord for '{name}' is empty. "
                f"The file may be corrupted: '{path}'"
            )
        return assistant_id

    def create(self, name: str, id: str) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self._path(name), 'w') as f:
            f.write(id)
        print(f"AgentRecord '{name}' saved locally with ID: '{id}'")

    def list_names(self) -> list[str]:
        if not os.path.exists(self.base_dir):
            return []
        names = []
        for filename in os.listdir(self.base_dir):
            if filename.startswith("assistant_") and filename.endswith(".txt"):
                names.append(filename[len("assistant_"):-len(".txt")])
        return names

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not os.path.exists(path):
            print(f"AgentRecord did not exist: '{path}'")
            return False
        os.remove(path)
        print(f"AgentRecord deleted: '{path}'")
        return True
