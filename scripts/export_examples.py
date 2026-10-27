from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from interactions import InteractionStore
from interactions.examples import answer_examples, preference_pairs

DEFAULT_OUT_DIR = Path("data/exports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export answers employees rated or HR reviewed, for evaluating and training the assistant. "
        "Writes examples.jsonl (every rated or reviewed answer) and preference_pairs.jsonl "
        "(answers HR rewrote, in OpenAI's DPO fine-tuning format)."
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Where to write the files.")
    return parser.parse_args()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    load_dotenv()
    args = parse_args()
    examples = answer_examples(InteractionStore())
    pairs = preference_pairs(examples)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / "examples.jsonl", examples)
    write_jsonl(args.out_dir / "preference_pairs.jsonl", pairs)

    unhelpful = sum(example["feedback"] == "down" for example in examples)
    reviewed = sum(example["review_verdict"] is not None for example in examples)
    print(f"{len(examples)} rated or reviewed answers ({unhelpful} marked unhelpful, {reviewed} reviewed by HR).")
    print(f"{len(pairs)} preference pairs from answers HR rewrote.")
    print(f"Written to {args.out_dir}/")


if __name__ == "__main__":
    main()
