"""Upload every fixture in evals/fixtures/ to a LangSmith dataset.

Re-running replaces the dataset, so edited labels always take effect.
Usage: python -m evals.upload_dataset
"""
import json
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "careerlens-matching"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def main() -> None:
    load_dotenv()
    client = Client()

    if client.has_dataset(dataset_name=DATASET_NAME):
        client.delete_dataset(dataset_name=DATASET_NAME)
    dataset = client.create_dataset(
        DATASET_NAME,
        description="Frozen Score/Dreamer inputs with hand-labelled job bands.",
    )

    fixtures = sorted(FIXTURES_DIR.glob("*.json"))
    examples = []
    for path in fixtures:
        fixture = json.loads(path.read_text())
        examples.append({
            "inputs": fixture["inputs"],
            "outputs": {"labels": fixture["labels"]},
            "metadata": {"case": path.stem},
        })
    client.create_examples(dataset_id=dataset.id, examples=examples)
    print(f"Uploaded {len(examples)} example(s) to {DATASET_NAME!r}")


if __name__ == "__main__":
    main()
