from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any


BLIND_CSV = "human_review_blind.csv"
KEY_JSON = "human_review_key.json"
MERGED_CSV = "human_ratings_merged.csv"
RATING_COLUMNS = ("language_quality_1_5", "usefulness_1_5")


def export_blind_review(
    raw_rows: list[dict[str, Any]],
    results_dir: Path,
    per_language: int = 5,
    random_seed: int = 42,
) -> Path:
    candidates: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in raw_rows:
        if row.get("is_warmup") or row.get("error") or not row.get("response"):
            continue
        model_id = row["model_id"]
        language = row.get("language_style", "unknown")
        prompt_id = row["prompt_id"]
        previous = candidates[(model_id, language)].get(prompt_id)
        if previous is None or (row.get("repeat") or 10**9) < (previous.get("repeat") or 10**9):
            candidates[(model_id, language)][prompt_id] = row

    model_ids = sorted({model_id for model_id, _ in candidates})
    rng = random.Random(random_seed)
    shuffled_models = model_ids[:]
    rng.shuffle(shuffled_models)
    aliases = {model_id: f"BLIND_{index:03d}" for index, model_id in enumerate(shuffled_models, start=1)}
    selected = []
    for (model_id, language), prompts in sorted(candidates.items()):
        samples = list(prompts.values())
        rng.shuffle(samples)
        selected.extend((model_id, row) for row in samples[:per_language])
    rng.shuffle(selected)

    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / BLIND_CSV
    fields = (
        "rating_id", "blind_model", "prompt_id", "task_type", "language_style",
        "benchmark_input", "response", *RATING_COLUMNS, "comments",
    )
    key: dict[str, str] = {}
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index, (model_id, row) in enumerate(selected, start=1):
            rating_id = f"RATE_{index:04d}"
            key[rating_id] = model_id
            messages = row.get("messages", [])
            writer.writerow(
                {
                    "rating_id": rating_id,
                    "blind_model": aliases[model_id],
                    "prompt_id": row.get("prompt_id"),
                    "task_type": row.get("task_type"),
                    "language_style": row.get("language_style"),
                    "benchmark_input": messages[-1].get("content", "") if messages else "",
                    "response": row.get("response", ""),
                    "language_quality_1_5": "",
                    "usefulness_1_5": "",
                    "comments": "",
                }
            )
    (results_dir / KEY_JSON).write_text(
        json.dumps(key, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def merge_blind_ratings(
    ratings_path: Path,
    results_dir: Path,
) -> Path:
    key_path = results_dir / KEY_JSON
    if not key_path.is_file():
        raise FileNotFoundError(f"Blind key not found: {key_path}")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    with ratings_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        input_fields = reader.fieldnames or []
        missing = {"rating_id", *RATING_COLUMNS} - set(input_fields)
        if missing:
            raise ValueError(f"Ratings CSV is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    merged_fields = list(input_fields) + ["model_id"]
    output_path = results_dir / MERGED_CSV
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=merged_fields)
        writer.writeheader()
        for row in rows:
            model_id = key.get(row["rating_id"])
            if model_id is None:
                raise ValueError(f"Unknown rating_id in blind CSV: {row['rating_id']}")
            for column in RATING_COLUMNS:
                value = row.get(column, "").strip()
                if value and (not value.isdigit() or not 1 <= int(value) <= 5):
                    raise ValueError(f"{column} must be an integer from 1 to 5 ({row['rating_id']})")
            writer.writerow({**row, "model_id": model_id})
    return output_path
