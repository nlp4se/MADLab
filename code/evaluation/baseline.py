import pandas as pd
import os
from tqdm import tqdm
import argparse
from dotenv import load_dotenv

from ..core.agent_caller import AgentCaller
from ..infrastructure.openai.openai_agent_caller import OpenAIAgentCaller
from ..infrastructure.persistence.file_agent_record import FileAgentRecord


def process_dataset(
    input_path: str,
    output_folder: str,
    batch_size: int,
    assistant_name: str,
    model: str = "gpt-4o"
) -> None:
    """
    Process a dataset in batches using an OpenAI-backed assistant.

    Args:
        input_path: Path to input CSV file
        output_folder: Path to output folder
        batch_size: Number of rows to process in each batch
        assistant_name: Name of the assistant to use
        model: Model to use for the assistant
    """
    print(f"Loading dataset from {input_path}")
    df = pd.read_csv(input_path)

    load_dotenv()
    agent_record = FileAgentRecord()
    external_caller = OpenAIAgentCaller(api_key=os.getenv("OPENAI_API_KEY"))
    caller = AgentCaller(external_caller=external_caller, agent_record=agent_record)

    os.makedirs(output_folder, exist_ok=True)

    n_batches = (len(df) + batch_size - 1) // batch_size
    print(f"Processing {len(df)} rows in {n_batches} batches")

    df['assistant_label'] = None

    for i in tqdm(range(0, len(df), batch_size)):
        batch = df.iloc[i:i+batch_size]

        requirements = batch['requirement'].tolist()

        response, _ = caller.submit_message(
            str(requirements),
            assistant_name=assistant_name,
            model=model
        )

        try:
            response_dict = eval(response)  # or you could use json.loads(response)
            labels = response_dict['classes']

            if len(labels) != len(batch):
                print(f"Warning: Batch {i//batch_size + 1} - Response length mismatch")
                continue

            df.loc[i:i+batch_size-1, 'assistant_label'] = labels

        except Exception as e:
            print(f"Error processing batch {i//batch_size + 1}: {e}")
            continue

    output_path = os.path.join(output_folder, os.path.basename(input_path))
    df.to_csv(output_path, index=False)
    print(f"Results saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Process dataset using OpenAI assistant')
    parser.add_argument('--input_path', required=True,
                       help='Path to input CSV file')
    parser.add_argument('--output_folder', required=True,
                       help='Path to output folder')
    parser.add_argument('--batch_size', type=int, default=10,
                       help='Number of rows to process in each batch')
    parser.add_argument('--assistant_name', required=True,
                       help='Name of the assistant to use')
    parser.add_argument('--model', default='gpt-4o',
                       help='Model to use (e.g., gpt-4o)')

    args = parser.parse_args()

    process_dataset(
        input_path=args.input_path,
        output_folder=args.output_folder,
        batch_size=args.batch_size,
        assistant_name=args.assistant_name,
        model=args.model
    )


if __name__ == "__main__":
    main()
