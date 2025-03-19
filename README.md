# llm-discussion

A project for creating AI assistants using Large Language Models for discussion.

## Setup

1. Clone the repository:
```bash
git clone https://github.com/nlp4se/llm-discussion.git
cd llm-discussion
```

2. Create a `.env` file in the root directory with your API keys:
```bash
OPENAI_API_KEY=your_openai_api_key_here
# Add other API keys as needed
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create assistants:

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name discussant1 --prompt_file_path .\data\prompts\discussant\system-prompt.txt

python.exe -m code.llm.openai.create_assistant_openai --assistant_name discussant2 --prompt_file_path .\data\prompts\discussant\system-prompt.txt

python.exe -m code.llm.openai.create_assistant_openai --assistant_name coordinator --prompt_file_path .\data\prompts\coordinator\system-prompt.txt
```

5. Use assistants:

```
python.exe -m code.llm.openai.ask_assistant_openai --assistant_name discussant1
```

6. Example of coordination (Summarization):

```
python.exe -m code.llm.coordinator --temperature 1
```