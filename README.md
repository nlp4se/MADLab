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

4. Create assistant:

```
python -m code.llm.openai.create_assistant_openai
```

5. Use assistant:

```
python.exe -m code.llm.openai.ask_assistant_openai 
```