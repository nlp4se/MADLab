import os
import sys
import argparse


class PromptFile:
    def __init__(self, base_dir: str = "data/prompts"):
        self.base_dir = base_dir

    def _path(self, prompt_path: str) -> str:
        return os.path.join(self.base_dir, prompt_path)

    def get_prompt(self, prompt_path: str) -> str:
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

    def create_prompt(self, prompt_path: str) -> None:
        full_path = self._path(prompt_path)
        print(f"Creating prompt at '{full_path}'")
        print("Enter prompt content (Ctrl+Z + Enter on Windows / Ctrl+D on Unix to finish):")
        content = sys.stdin.read()
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"Prompt created at '{full_path}'")

    def update_prompt(self, prompt_path: str) -> None:
        full_path = self._path(prompt_path)
        try:
            with open(full_path, 'r') as f:
                current_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Prompt file not found: '{full_path}'"
            )
        print(f"Current content of '{full_path}':")
        print("-" * 40)
        print(current_content)
        print("-" * 40)
        print("Enter new content (Ctrl+Z + Enter on Windows / Ctrl+D on Unix to finish):")
        content = sys.stdin.read()
        with open(full_path, 'w') as f:
            f.write(content)
        print(f"Prompt updated at '{full_path}'")

    def delete_prompt(self, prompt_path: str) -> bool:
        full_path = self._path(prompt_path)
        if not os.path.exists(full_path):
            print(f"Prompt file did not exist: '{full_path}'")
            return False
        os.remove(full_path)
        print(f"Prompt file deleted: '{full_path}'")
        return True


def main():
    parser = argparse.ArgumentParser(description='Manage prompt files.')
    parser.add_argument('action', choices=['create', 'update', 'delete', 'get'],
                        help='Action to perform on the prompt file')
    parser.add_argument('prompt_path',
                        help='Path to the prompt file relative to data/prompts/ (e.g. discussant/system-prompt.txt)')
    args = parser.parse_args()

    prompt_file = PromptFile()

    if args.action == 'create':
        prompt_file.create_prompt(args.prompt_path)
    elif args.action == 'update':
        prompt_file.update_prompt(args.prompt_path)
    elif args.action == 'delete':
        prompt_file.delete_prompt(args.prompt_path)
    elif args.action == 'get':
        print(prompt_file.get_prompt(args.prompt_path))


if __name__ == '__main__':
    main()
