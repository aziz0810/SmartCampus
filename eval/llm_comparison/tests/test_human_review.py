import csv
import json

from eval.llm_comparison.human_review import export_blind_review, merge_blind_ratings


def test_human_review_hides_model_ids_and_merges_ratings(tmp_path):
    rows = [
        {
            "model_id": model, "prompt_id": f"{language}-{model}", "task_type": "T4",
            "language_style": language, "response": "Sample", "repeat": 1,
            "messages": [{"role": "user", "content": "Synthetic prompt"}],
        }
        for model in ("model-a", "model-b")
        for language in ("fr", "ar_tn")
    ]
    blind_path = export_blind_review(rows, tmp_path, per_language=1)
    with blind_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        blind_rows = list(reader)
        assert "model_id" not in (reader.fieldnames or [])
    assert len(blind_rows) == 4

    filled_path = tmp_path / "filled.csv"
    with filled_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=blind_rows[0].keys())
        writer.writeheader()
        for row in blind_rows:
            row["language_quality_1_5"] = "4"
            row["usefulness_1_5"] = "5"
            writer.writerow(row)
    merged_path = merge_blind_ratings(filled_path, tmp_path)
    with merged_path.open(encoding="utf-8-sig", newline="") as stream:
        merged = list(csv.DictReader(stream))
    assert {row["model_id"] for row in merged} == {"model-a", "model-b"}
    assert all(row["language_quality_1_5"] == "4" for row in merged)
    assert json.loads((tmp_path / "human_review_key.json").read_text(encoding="utf-8"))

