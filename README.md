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

## Requirements classification with Persona pattern

1. Create the assistant.

Multi-class

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name persona_classifier_multiclass --prompt_file_path .\data\prompts\discussant\persona-system-prompt-multiclass.txt --schema_file_path .\data\prompts\discussant\requirements-schema-multiclass.json
```

or binary

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name persona_classifier_binary --prompt_file_path .\data\prompts\discussant\persona-system-prompt-binary.txt --schema_file_path .\data\prompts\discussant\requirements-schema-binary.json   
```

2. Test the assistant

Multi-class

```
python.exe -m code.llm.openai.ask_assistant_openai --assistant_name persona_classifier_multiclass --prompt_file .\data\prompts\discussant\persona-user-prompt.txt
```

or binary

```
python.exe -m code.llm.openai.ask_assistant_openai --assistant_name persona_classifier_binary --prompt_file .\data\prompts\discussant\persona-user-prompt.txt
```

3. Get the baseline ground-truth

Multi-class

```
python.exe -m code.evaluation.baseline --input_path .\data\datasets\PROMISE\nfr-multiclass.csv --output_folder .\data\output\baseline\multiclass\ --batch_size 10 --assistant_name persona_classifier_multiclass --model gpt-4o
```

or binary

```
python.exe -m code.evaluation.baseline --input_path .\data\datasets\PROMISE\nfr.csv --output_folder .\data\output\baseline\binary\ --batch_size 10 --assistant_name persona_classifier_binary --model gpt-4o
```

4. Get evaluation results

Multi-class

```
python.exe -m code.evaluation.metrics --input .\data\output\baseline\multiclass\nfr.csv --output .\data\evaluation\multiclass
```

or binary

```
python.exe -m code.evaluation.metrics --input .\data\output\baseline\binary\nfr.csv --output .\data\evaluation\binary
```

