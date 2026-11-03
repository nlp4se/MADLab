import os
import json
from dataclasses import asdict

from ...domain.contracts.agent_record import AgentRecord, AgentDefinition


class FileAgentRecord(AgentRecord):
    def __init__(self, base_dir: str = "data/agent_records"):
        self.base_dir = base_dir

    def _path(self, name: str) -> str:
        return os.path.join(self.base_dir, f"agent_{name}.json")

    def get(self, name: str) -> AgentDefinition:
        path = self._path(name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"No AgentRecord found for '{name}'. "
                f"Create the agent first with 'manage_agents.py create'."
            )
        except json.JSONDecodeError:
            raise ValueError(
                f"AgentRecord for '{name}' is not valid JSON. "
                f"The file may be corrupted: '{path}'"
            )
        try:
            return AgentDefinition(**data)
        except TypeError:
            raise ValueError(
                f"AgentRecord for '{name}' has missing or unexpected fields. "
                f"The file may be corrupted: '{path}'"
            )

    def save(self, agent: AgentDefinition) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        path = self._path(agent.name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(agent), f, indent=2, ensure_ascii=False)
        print(f"AgentRecord '{agent.name}' saved locally at '{path}'")

    def list_names(self) -> list[str]:
        if not os.path.exists(self.base_dir):
            return []
        names = []
        for filename in os.listdir(self.base_dir):
            if filename.startswith("agent_") and filename.endswith(".json"):
                names.append(filename[len("agent_"):-len(".json")])
        return names

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not os.path.exists(path):
            print(f"AgentRecord did not exist: '{path}'")
            return False
        os.remove(path)
        print(f"AgentRecord deleted: '{path}'")
        return True
