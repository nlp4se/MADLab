import sys
import argparse

from code.infrastructure.persistence.file_prompt_record import FilePromptRecord


def _read_stdin(label: str) -> str:
    print(f"{label} (Ctrl+Z + Enter on Windows / Ctrl+D on Unix to finish):")
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description='Manage prompt files.')
    subparsers = parser.add_subparsers(dest='action', required=True)

    create_parser = subparsers.add_parser('create', help='Create a new prompt file')
    create_parser.add_argument('--prompt-path', required=True,
                               help='Path to the prompt file relative to data/prompts/ (e.g. discussant/system-prompt.txt)')

    update_parser = subparsers.add_parser('update', help='Update an existing prompt file')
    update_parser.add_argument('--prompt-path', required=True,
                               help='Path to the prompt file relative to data/prompts/')

    delete_parser = subparsers.add_parser('delete', help='Delete a prompt file')
    delete_parser.add_argument('--prompt-path', required=True,
                               help='Path to the prompt file relative to data/prompts/')

    get_parser = subparsers.add_parser('get', help='Print the content of a prompt file')
    get_parser.add_argument('--prompt-path', required=True,
                            help='Path to the prompt file relative to data/prompts/')

    args = parser.parse_args()

    prompt_record = FilePromptRecord()

    if args.action == 'create':
        content = _read_stdin(f"Enter prompt content for '{args.prompt_path}'")
        prompt_record.create(args.prompt_path, content)
    elif args.action == 'update':
        current = prompt_record.get(args.prompt_path)
        print(f"Current content of '{args.prompt_path}':")
        print("-" * 40)
        print(current)
        print("-" * 40)
        content = _read_stdin("Enter new content")
        prompt_record.update(args.prompt_path, content)
    elif args.action == 'delete':
        prompt_record.delete(args.prompt_path)
    elif args.action == 'get':
        print(prompt_record.get(args.prompt_path))


if __name__ == '__main__':
    main()
