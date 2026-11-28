import json
from collections import Counter
from pathlib import Path

import pytest

from eval.llm_comparison import runner
from eval.llm_comparison.dataset.build_sa32 import OUTPUT_PATH, PROFILE_FIELDS, build_sa32
from eval.llm_comparison.dataset.loader import load_jsonl
from eval.llm_comparison.scoring import INTENT_LABELS, score_record

PROMPTS_DIR = Path(runner.__file__).with_name("prompts") / "v1"
CATEGORIES = {"admission", "orientation", "reformulation", "ambiguous"}


@pytest.fixture(scope="module")
def rows():
    return load_jsonl(OUTPUT_PATH)


def test_checked_in_file_matches_generator(rows):
    assert rows == json.loads(json.dumps(build_sa32()))


def test_size_language_and_categories(rows):
    assert len(rows) == 60
    assert {row["category"] for row in rows} == CATEGORIES
    french = sum(row["language_style"] == "fr" for row in rows)
    assert french / len(rows) >= 0.7
    assert all(row["needs_native_review"] == (row["language_style"] != "fr") for row in rows)
    assert all(row["id"].startswith("sa32-") for row in rows)


def test_fields_match_what_the_scorer_reads(rows):
    for row in rows:
        expected = row["expected"]
        task = row["task_type"]
        if task == "T1":
            assert expected["intent"] in INTENT_LABELS
        elif task == "T2":
            assert set(expected["profile"]) == set(PROFILE_FIELDS)
        elif task == "T3":
            assert {"unanswerable", "source_ids", "required_facts", "forbidden_facts",
                    "injection_expected_ignored"} <= set(expected)
            if expected["unanswerable"]:
                assert expected["not_available_markers"]
        elif task == "T4":
            assert expected["required_literal"]
        elif task == "T5":
            assert expected["required_facts"] and expected["reask_markers"]
            assert len(row["history"]) == 4
        else:
            pytest.fail(f"unknown task type {task}")


def test_paraphrase_groups_have_consistent_gold(rows):
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if row["paraphrase_group"]:
            groups.setdefault(row["paraphrase_group"], []).append(row)
    assert len(groups) >= 4
    for members in groups.values():
        assert len(members) >= 3
        assert len({json.dumps(m["expected"], sort_keys=True) for m in members}) == 1


def test_admission_excerpts_reach_the_model(rows):
    system_prompt = (PROMPTS_DIR / "system.txt").read_text(encoding="utf-8")
    user_template = (PROMPTS_DIR / "user_template.txt").read_text(encoding="utf-8")
    row = next(r for r in rows if r["context"]["sources"] and r["context"]["sources"][0]["id"] == "ADM-GINFO")
    messages = runner.build_messages(row, system_prompt, user_template)
    assert "[ADM-GINFO] excerpt:" in messages[-1]["content"]
    assert "Informatique de gestion" in messages[-1]["content"]


def test_every_row_can_be_scored(rows):
    for row in rows:
        score = score_record({"response": '{"intent": "program_info"}', "error": None}, row)
        assert score["success"] is True


def test_reference_answers_score_correctly(rows):
    by_id = {row["id"]: row for row in rows}
    grounded = by_id["sa32-adm-06"]
    answer = {"answer": "Oui, la licence Informatique de gestion est acceptée.", "sources": ["ADM-GINFO"]}
    score = score_record({"response": json.dumps(answer, ensure_ascii=False), "error": None}, grounded)
    assert score["citation_correct"] and score["grounded_fact_match"]

    fees = by_id["sa32-adm-15"]
    answer = {"answer": "Les frais ne sont pas disponible dans le contexte : information non disponible.", "sources": []}
    score = score_record({"response": json.dumps(answer, ensure_ascii=False), "error": None}, fees)
    assert score["not_available_correct"] and score["citation_correct"]


def test_task_mix(rows):
    tasks = Counter(row["task_type"] for row in rows)
    assert set(tasks) == {"T1", "T2", "T3", "T4", "T5"}
