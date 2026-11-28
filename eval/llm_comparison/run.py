from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval.llm_comparison.config import (
    DEFAULT_DATASET_FILE,
    DEFAULT_MODELS_FILE,
    DEFAULT_RESULTS_DIR,
    load_models_file,
    resolve_input_path,
)
from eval.llm_comparison.dataset.loader import load_jsonl
from eval.llm_comparison.human_review import BLIND_CSV, export_blind_review, merge_blind_ratings
from eval.llm_comparison.report import write_artifacts
from eval.llm_comparison.runner import _read_raw, run_benchmark


def _latest_run(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.exists():
        return {}
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        runs = data.get("runs", [])
        return runs[-1] if runs else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _has_filled_review(path: Path) -> bool:
    if not path.is_file():
        return False
    import csv

    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("language_quality_1_5", "").strip() or row.get("usefulness_1_5", "").strip() or row.get("comments", "").strip():
                return True
    return False


def _current_raw_rows(
    raw_rows: list[dict[str, Any]],
    *,
    dataset_hash: str,
    prompt_hash: str,
    params_hash: str,
    prompt_ids: set[str],
    models: list[Any],
    repeats: int,
) -> list[dict[str, Any]]:
    tags = {model.id: model.tag for model in models}
    return [
        row for row in raw_rows
        if row.get("dataset_hash") == dataset_hash
        and row.get("prompt_hash") == prompt_hash
        and row.get("params_hash") == params_hash
        and row.get("model_id") in tags
        and row.get("model_tag") == tags[row["model_id"]]
        and (row.get("is_warmup") or (row.get("prompt_id") in prompt_ids and isinstance(row.get("repeat"), int) and row["repeat"] <= repeats))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or report the SmartCampus local LLM benchmark.")
    parser.add_argument("--models", type=Path, default=DEFAULT_MODELS_FILE)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_FILE)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--limit-prompts", type=int)
    parser.add_argument("--model", action="append", dest="models_only", help="Model id to run; may be repeated")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--export-human", action="store_true", help="Create a blinded human-rating CSV from existing successful runs")
    modes.add_argument("--merge-human", type=Path, help="Merge a filled blind-rating CSV into results")
    args = parser.parse_args()

    models_path = resolve_input_path(args.models)
    dataset_path = resolve_input_path(args.dataset)
    config = load_models_file(models_path)
    models = [model for model in config.models if model.enabled and (not args.models_only or model.id in args.models_only)]
    dataset = load_jsonl(dataset_path)
    raw_path = args.results_dir / "raw_runs.jsonl"
    metadata_path = args.results_dir / "run_metadata.json"

    if args.export_human:
        rows = _read_raw(raw_path)
        successful = [row for row in rows if not row.get("is_warmup") and not row.get("error") and row.get("response")]
        if not successful:
            raise SystemExit("No successful raw responses are available to rate yet.")
        output = export_blind_review(
            rows,
            args.results_dir,
            per_language=config.benchmark.human_sample_per_language,
            random_seed=config.benchmark.random_seed,
        )
        print(f"Wrote blinded ratings sheet: {output}")
        return

    if args.merge_human:
        ratings_path = args.merge_human if args.merge_human.is_absolute() else Path.cwd() / args.merge_human
        merged_path = merge_blind_ratings(ratings_path, args.results_dir)
        latest = _latest_run(metadata_path)
        rows = _read_raw(raw_path)
        write_artifacts(
            raw_rows=rows,
            dataset=dataset,
            models=models,
            model_status=latest.get("model_status", {}),
            weights=config.benchmark.weights,
            results_dir=args.results_dir,
            requested_repeats=latest.get("requested_repeats", args.repeats or config.benchmark.repeats),
            run_metadata=latest,
        )
        print(f"Merged ratings: {merged_path}")
        print(f"Updated report: {args.results_dir / 'report.md'}")
        return

    result = run_benchmark(
        models_path=models_path,
        dataset_path=dataset_path,
        results_dir=args.results_dir,
        repeats=args.repeats,
        limit_prompts=args.limit_prompts,
        model_ids=set(args.models_only) if args.models_only else None,
    )
    selected_dataset = dataset[:args.limit_prompts] if args.limit_prompts else dataset
    all_raw_rows = _read_raw(result["raw_path"])
    raw_rows = _current_raw_rows(
        all_raw_rows,
        dataset_hash=result["dataset_hash"],
        prompt_hash=result["prompt_hash"],
        params_hash=result["params_hash"],
        prompt_ids={item["id"] for item in selected_dataset},
        models=models,
        repeats=result["repeats"],
    )
    latest = _latest_run(result["metadata_path"])

    blind_path = args.results_dir / BLIND_CSV
    successful = [row for row in raw_rows if not row.get("is_warmup") and not row.get("error") and row.get("response")]
    if successful and not _has_filled_review(blind_path):
        export_blind_review(
            raw_rows,
            args.results_dir,
            per_language=config.benchmark.human_sample_per_language,
            random_seed=config.benchmark.random_seed,
        )

    summary = write_artifacts(
        raw_rows=raw_rows,
        dataset=selected_dataset,
        models=models,
        model_status=result["model_status"],
        weights=config.benchmark.weights,
        results_dir=args.results_dir,
        requested_repeats=result["repeats"],
        run_metadata=latest,
    )
    statuses = ", ".join(f"{model_id}={status.get('status')}" for model_id, status in result["model_status"].items())
    print(f"Raw calls: {sum(not row.get('is_warmup') for row in raw_rows)}")
    print(f"Summary rows: {len(summary)}")
    print(f"Model status: {statuses or 'no enabled models selected'}")
    print(f"Report: {args.results_dir / 'report.md'}")


if __name__ == "__main__":
    main()
