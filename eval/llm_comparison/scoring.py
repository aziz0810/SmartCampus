from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator

from eval.llm_comparison.config import ModelSpec

INTENT_LABELS = {
    "program_info", "comparison", "orientation", "preregistration",
    "appointment", "smalltalk", "out_of_scope", "human_handoff",
}
PROFILE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "academic_level", "favorite_subjects", "interests", "career_goal",
        "constraints", "preferred_language",
    ],
    "additionalProperties": False,
    "properties": {
        "academic_level": {"type": ["string", "null"]},
        "favorite_subjects": {"type": ["array", "null"], "items": {"type": "string"}},
        "interests": {"type": ["array", "null"], "items": {"type": "string"}},
        "career_goal": {"type": ["string", "null"]},
        "constraints": {"type": ["array", "null"], "items": {"type": "string"}},
        "preferred_language": {"type": ["string", "null"]},
    },
}
PROFILE_VALIDATOR = Draft202012Validator(PROFILE_SCHEMA)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(" " if unicodedata.category(char).startswith("P") else char for char in normalized)
    return " ".join(without_punctuation.split())


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _profile_atoms(profile: dict[str, Any]) -> set[str]:
    atoms: set[str] = set()
    for key, value in profile.items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        atoms.update(f"{key}={normalize_text(str(item))}" for item in values)
    return atoms


def _prf(expected: set[str], predicted: set[str]) -> tuple[float, float, float]:
    true_positive = len(expected & predicted)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _has_any(text: str, phrases: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(phrase) in normalized for phrase in phrases)


def score_record(record: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response") or ""
    result: dict[str, Any] = {
        "success": record.get("error") is None and bool(response.strip()),
        "error_type": (record.get("error") or {}).get("type"),
        "json_valid": None,
        "schema_valid": None,
        "intent_correct": None,
        "profile_precision": None,
        "profile_recall": None,
        "profile_f1": None,
        "not_available_correct": None,
        "citation_correct": None,
        "grounded_fact_match": None,
        "injection_resistance": None,
        "program_name_preserved": None,
        "arabic_script_detected_heuristic": None,
        "known_facts_present_heuristic": None,
        "no_reask_heuristic": None,
    }
    task = item["task_type"]
    expected = item.get("expected", {})

    if task in {"T1", "T2", "T3"}:
        parsed = parse_json_object(response)
        result["json_valid"] = parsed is not None
        if task == "T1":
            label = parsed.get("intent") if parsed else None
            result["schema_valid"] = isinstance(label, str) and label in INTENT_LABELS and set(parsed) == {"intent"}
            result["intent_correct"] = label == expected.get("intent")
        elif task == "T2":
            # T2 returns the six profile fields at the top level, without a wrapper.
            profile = parsed
            schema_valid = isinstance(profile, dict) and not list(PROFILE_VALIDATOR.iter_errors(profile))
            result["schema_valid"] = schema_valid
            prediction = profile if isinstance(profile, dict) else {}
            precision, recall, f1 = _prf(
                _profile_atoms(expected.get("profile", {})),
                _profile_atoms(prediction),
            )
            result.update({"profile_precision": precision, "profile_recall": recall, "profile_f1": f1})
        elif task == "T3":
            answer = parsed.get("answer", "") if parsed else ""
            source_ids = parsed.get("sources") if parsed else None
            schema_valid = isinstance(answer, str) and isinstance(source_ids, list) and all(isinstance(v, str) for v in source_ids)
            result["schema_valid"] = schema_valid
            if expected.get("unanswerable"):
                result["not_available_correct"] = _has_any(answer, expected.get("not_available_markers", []))
                result["citation_correct"] = set(source_ids or []) == set(expected.get("source_ids", []))
            else:
                expected_sources = set(expected.get("source_ids", []))
                result["citation_correct"] = set(source_ids or []) == expected_sources
                facts = expected.get("required_facts", [])
                result["grounded_fact_match"] = all(fact in answer for fact in facts)
            if expected.get("injection_expected_ignored"):
                result["injection_resistance"] = not _has_any(answer, expected.get("forbidden_facts", []))
    elif task == "T4":
        required_literal = expected.get("required_literal", "")
        result["program_name_preserved"] = bool(required_literal) and required_literal in response
        if expected.get("expected_script") == "arabic":
            result["arabic_script_detected_heuristic"] = any(
                "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f" or "\u08a0" <= char <= "\u08ff"
                for char in response
            )
    elif task == "T5":
        result["known_facts_present_heuristic"] = all(
            normalize_text(fact) in normalize_text(response)
            for fact in expected.get("required_facts", [])
        )
        result["no_reask_heuristic"] = bool(response.strip()) and not _has_any(response, expected.get("reask_markers", []))
    return result


def score_runs(raw_rows: list[dict[str, Any]], dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_by_id = {item["id"]: item for item in dataset}
    scored = []
    for record in raw_rows:
        if record.get("is_warmup"):
            continue
        item = item_by_id.get(record.get("prompt_id"))
        if item is None:
            continue
        scored.append({**record, "metrics": score_record(record, item)})
    return scored


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row["metrics"][key]) for row in rows if isinstance(row.get("metrics", {}).get(key), (int, float))]
    return sum(values) / len(values) if values else None


def _quantile(rows: list[dict[str, Any]], key: str, quantile: float) -> float | None:
    values = [row.get("timings", {}).get(key) for row in rows]
    values = [float(value) for value in values if isinstance(value, (int, float))]
    return float(pd.Series(values).quantile(quantile)) if values else None


def _consistency(rows: list[dict[str, Any]]) -> float | None:
    by_prompt: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.get("response"):
            by_prompt[row["prompt_id"]].append(normalize_text(row["response"]))
    prompt_scores = []
    for responses in by_prompt.values():
        if len(responses) > 1:
            prompt_scores.append(Counter(responses).most_common(1)[0][1] / len(responses))
    return sum(prompt_scores) / len(prompt_scores) if prompt_scores else None


def _group_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    call_count = len(rows)
    failures = sum(row.get("error") is not None or not (row.get("response") or "").strip() for row in rows)
    json_rows = [row for row in rows if row.get("task_type") in {"T1", "T2", "T3"}]
    json_failures = sum(not row.get("metrics", {}).get("json_valid") for row in json_rows)
    timings_rows = [row for row in rows if row.get("error") is None]
    metric_keys = (
        "intent_correct", "profile_precision", "profile_recall", "profile_f1",
        "not_available_correct", "citation_correct", "grounded_fact_match",
        "injection_resistance", "program_name_preserved",
        "arabic_script_detected_heuristic", "known_facts_present_heuristic", "no_reask_heuristic",
    )
    values = {key: _mean(rows, key) for key in metric_keys}
    values["json_valid_rate"] = _mean(rows, "json_valid")
    values["schema_valid_rate"] = _mean(rows, "schema_valid")
    quality_by_task = []
    task_metrics = {
        "T1": ["intent_correct"],
        "T2": ["json_valid", "schema_valid", "profile_f1"],
        "T3": ["not_available_correct", "citation_correct", "grounded_fact_match", "injection_resistance"],
        "T4": ["program_name_preserved", "arabic_script_detected_heuristic"],
        "T5": ["known_facts_present_heuristic", "no_reask_heuristic"],
    }
    for task, keys in task_metrics.items():
        task_rows = [row for row in rows if row.get("task_type") == task]
        if not task_rows:
            continue
        present = [_mean(task_rows, key) for key in keys]
        present = [value for value in present if value is not None]
        if present:
            quality_by_task.append(sum(present) / len(present))
    quality_score = sum(quality_by_task) / len(quality_by_task) if quality_by_task else None
    costs = [row.get("cost_usd") for row in rows if isinstance(row.get("cost_usd"), (int, float))]
    output_rates = [row.get("timings", {}).get("output_tokens_per_second") for row in timings_rows]
    output_rates = [float(value) for value in output_rates if isinstance(value, (int, float))]
    load_durations = [row.get("timings", {}).get("load_duration_s") for row in timings_rows]
    load_durations = [float(value) for value in load_durations if isinstance(value, (int, float))]
    return {
        "n_runs": call_count,
        "n_success": call_count - failures,
        "error_rate": failures / call_count if call_count else None,
        "json_failure_rate": json_failures / len(json_rows) if json_rows else None,
        **values,
        "consistency_rate": _consistency(rows),
        "p50_latency_s": _quantile(timings_rows, "wall_latency_s", 0.50),
        "p95_latency_s": _quantile(timings_rows, "wall_latency_s", 0.95),
        "p50_ttft_s": _quantile(timings_rows, "ttft_s", 0.50),
        "p95_ttft_s": _quantile(timings_rows, "ttft_s", 0.95),
        "mean_output_tokens_per_second": sum(output_rates) / len(output_rates) if output_rates else None,
        "mean_load_duration_s": sum(load_durations) / len(load_durations) if load_durations else None,
        "cost_usd_per_1000_requests": sum(costs) * 1000 / len(costs) if costs else None,
        "quality_score": quality_score,
    }


def build_summary(
    scored_rows: list[dict[str, Any]],
    models: list[ModelSpec],
    dataset: list[dict[str, Any]],
    model_status: dict[str, dict[str, Any]],
    weights: dict[str, float],
) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    combinations = sorted({(item["task_type"], item["language_style"]) for item in dataset})
    for model in models:
        model_rows = [row for row in scored_rows if row.get("model_id") == model.id]
        groups: list[tuple[str, str, list[dict[str, Any]]]] = [("ALL", "ALL", model_rows)]
        groups.extend(
            (task, language, [row for row in model_rows if row.get("task_type") == task and row.get("language_style") == language])
            for task, language in combinations
        )
        for task, language, rows in groups:
            metrics = _group_metrics(rows)
            status = model_status.get(model.id, {}).get("status", "not_run")
            output.append(
                {
                    "provider": model.provider,
                    "model_id": model.id,
                    "model_tag": model.tag,
                    "status": status,
                    "task_type": task,
                    "language_style": language,
                    **metrics,
                    "latency_score": None,
                    "cost_score": None,
                    "reliability_score": 1 - metrics["error_rate"] if metrics["error_rate"] is not None else None,
                    "weighted_score": None,
                }
            )

    frame = pd.DataFrame(output)
    if frame.empty:
        return frame
    overall = frame[(frame["task_type"] == "ALL") & (frame["language_style"] == "ALL")]
    provider_min_latency = overall.groupby("provider")["p50_latency_s"].min().to_dict()
    provider_max_cost = overall.groupby("provider")["cost_usd_per_1000_requests"].max().to_dict()
    for index, row in overall.iterrows():
        latency = row["p50_latency_s"]
        min_latency = provider_min_latency.get(row["provider"])
        if pd.notna(latency) and latency > 0 and pd.notna(min_latency):
            frame.at[index, "latency_score"] = min(1.0, float(min_latency) / float(latency))
        cost = row["cost_usd_per_1000_requests"]
        max_cost = provider_max_cost.get(row["provider"])
        if pd.notna(cost) and pd.notna(max_cost):
            frame.at[index, "cost_score"] = 1.0 if float(max_cost) == 0 else max(0.0, 1 - float(cost) / float(max_cost))
        components = {
            "quality": row["quality_score"],
            "latency": frame.at[index, "latency_score"],
            "cost": frame.at[index, "cost_score"],
            "reliability": frame.at[index, "reliability_score"],
        }
        available = [(weights[name], value) for name, value in components.items() if name in weights and pd.notna(value)]
        if available and sum(weight for weight, _ in available) > 0:
            frame.at[index, "weighted_score"] = sum(weight * float(value) for weight, value in available) / sum(weight for weight, _ in available)
    return frame
