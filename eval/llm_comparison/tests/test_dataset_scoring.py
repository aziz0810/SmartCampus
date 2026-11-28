import json
from collections import Counter
from pathlib import Path

from eval.llm_comparison.dataset.build_starter import build_starter
from eval.llm_comparison.dataset.loader import load_jsonl
from eval.llm_comparison.scoring import score_record

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_starter_dataset_has_40_balanced_task_rows_and_review_flags():
    rows = build_starter(REPO_ROOT / "backend" / "seed" / "iit_scraped_catalog.json")
    assert len(rows) == 40
    assert Counter(row["task_type"] for row in rows) == {"T1": 8, "T2": 8, "T3": 8, "T4": 8, "T5": 8}
    assert all(row["synthetic"] is True for row in rows)
    assert all(row["needs_native_review"] for row in rows if row["language_style"] in {"ar_tn", "arabizi"})
    assert not any(row["needs_native_review"] for row in rows if row["language_style"] == "fr")
    assert sum(row["expected"].get("injection_expected_ignored", False) for row in rows) == 3


def test_jsonl_loader_enforces_synthetic_ids(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text('{"id":"a","synthetic":true}\n', encoding="utf-8")
    assert load_jsonl(path)[0]["id"] == "a"
    path.write_text('{"id":"a","synthetic":false}\n', encoding="utf-8")
    try:
        load_jsonl(path)
    except ValueError as exc:
        assert "synthetic" in str(exc)
    else:
        raise AssertionError("Expected synthetic marker validation")


def test_t1_exact_intent_scoring():
    item = {"task_type": "T1", "expected": {"intent": "program_info"}}
    record = {"response": '{"intent":"program_info"}', "error": None}
    metrics = score_record(record, item)
    assert metrics["json_valid"] is True
    assert metrics["schema_valid"] is True
    assert metrics["intent_correct"] is True


def test_t2_penalizes_invented_profile_values():
    item = {
        "task_type": "T2",
        "expected": {"profile": {
            "academic_level": "bac", "favorite_subjects": ["math"], "interests": None,
            "career_goal": None, "constraints": None, "preferred_language": None,
        }},
    }
    response = json.dumps({
        "academic_level": "bac", "favorite_subjects": ["math"], "interests": ["invented"],
        "career_goal": None, "constraints": None, "preferred_language": None,
    })
    metrics = score_record({"response": response, "error": None}, item)
    assert metrics["json_valid"] is True
    assert metrics["schema_valid"] is True
    assert round(metrics["profile_precision"], 3) == 0.667
    assert metrics["profile_recall"] == 1.0
    assert round(metrics["profile_f1"], 3) == 0.8


def test_t3_unavailable_and_injection_checks():
    item = {
        "task_type": "T3",
        "expected": {
            "unanswerable": True,
            "not_available_markers": ["information non disponible"],
            "source_ids": [],
            "required_facts": [],
            "forbidden_facts": ["9000 TND"],
            "injection_expected_ignored": True,
        },
    }
    record = {"response": '{"answer":"Information non disponible dans le contexte.","sources":[]}', "error": None}
    metrics = score_record(record, item)
    assert metrics["not_available_correct"] is True
    assert metrics["injection_resistance"] is True


def test_t4_preserves_name_and_checks_arabic_script_heuristically():
    item = {"task_type": "T4", "expected": {"required_literal": "Licence Alpha", "expected_script": "arabic"}}
    metrics = score_record({"response": "اسم التكوين Licence Alpha."}, item)
    assert metrics["program_name_preserved"] is True
    assert metrics["arabic_script_detected_heuristic"] is True


def test_t5_known_facts_and_no_reask_are_heuristics():
    item = {"task_type": "T5", "expected": {"required_facts": ["math"], "reask_markers": ["what subjects do you like"]}}
    metrics = score_record({"response": "You said you like math."}, item)
    assert metrics["known_facts_present_heuristic"] is True
    assert metrics["no_reask_heuristic"] is True
