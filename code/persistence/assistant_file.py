import os


class AssistantFile:
    def __init__(self, base_dir: str = "data/assistant_records"):
        self.base_dir = base_dir

    def _path(self, assistant_name: str) -> str:
        return os.path.join(self.base_dir, f"assistant_{assistant_name}.txt")

    def get_assistant_record_id(self, assistant_name: str) -> str:
        path = self._path(assistant_name)
        try:
            with open(path, 'r') as f:
                assistant_id = f.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"No AssistantRecord found for '{assistant_name}'. "
                f"Make sure the OpenAI Assistant has been created and registered first."
            )
        if not assistant_id:
            raise ValueError(
                f"AssistantRecord for '{assistant_name}' is empty. "
                f"The file may be corrupted: '{path}'"
            )
        return assistant_id

    def create_assistant_record(self, assistant_name: str, assistant_id: str) -> None:
        os.makedirs(self.base_dir, exist_ok=True)
        with open(self._path(assistant_name), 'w') as f:
            f.write(assistant_id)
        print(f"AssistantRecord '{assistant_name}' saved locally with ID: '{assistant_id}'")


    def get_all_assistant_records(self) -> list[str]:
        if not os.path.exists(self.base_dir):
            return []
        names = []
        for filename in os.listdir(self.base_dir):
            if filename.startswith("assistant_") and filename.endswith(".txt"):
                names.append(filename[len("assistant_"):-len(".txt")])
        return names

    def delete_assistant_record(self, assistant_name: str) -> bool:
        path = self._path(assistant_name)
        if not os.path.exists(path):
            print(f"AssistantRecord did not exist: '{path}'")
            return False
        os.remove(path)
        print(f"AssistantRecord deleted: '{path}'")
        return True
