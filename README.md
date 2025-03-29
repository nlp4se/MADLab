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
python.exe -m code.llm.openai.ask_assistant_openai --assistant_name discussant1 --promp_file_path .\data\prompts\discussant\requirement-example-prompt.txt
```

6. Example of coordination (Summarization):

```
python.exe -m code.llm.coordinator --input .\data\datasets\PROMISE\nfr-small.csv --output .\data\output\judge\binary\nfr-small.csv --assistants-file .\data\config\assistants.json --judge-file .\data\config\judge.json --temperature 0
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
python.exe -m code.evaluation.metrics --input .\data\output\baseline\multiclass\nfr-multiclass.csv --output .\data\evaluation\multiclass
```

or binary

```
python.exe -m code.evaluation.metrics --input .\data\output\baseline\binary\nfr.csv --output .\data\evaluation\binary
```

## Requirements classification with Judge pattern

Create the functional (F) debater assistant:

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name functional-debater --prompt_file_path .\data\prompts\discussant\functional-debater-prompt.txt   
```

Create the non-functional (NF) debater assistant:

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name non-functional-debater --prompt_file_path .\data\prompts\discussant\non-functional-debater-prompt.txt                     
```

Create the judge assistant:

```
python.exe -m code.llm.openai.create_assistant_openai --assistant_name judge-debater --prompt_file_path .\data\prompts\coordinator\judge-prompt.txt --schema_file_path .\data\prompts\coordinator\requirements-schema-binary.json    
```

Run the Judge discussion pattern (small dataset):

```
python.exe -m code.llm.coordinator --input .\data\datasets\PROMISE\nfr-small.csv --output .\data\output\judge\binary\nfr-small.csv --assistants-file .\data\config\assistants.json --judge-file .\data\config\judge.json --temperature 0   
```