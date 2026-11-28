from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd

from eval.llm_comparison.config import ModelSpec
from eval.llm_comparison.scoring import build_summary, score_runs


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _pct(value: Any) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{100 * float(value):.1f}%"


def _markdown_table(frame: pd.DataFrame, columns: list[str], headers: list[str], limit: int | None = None) -> list[str]:
    view = frame[columns].copy() if not frame.empty else pd.DataFrame(columns=columns)
    if limit:
        view = view.head(limit)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in view.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return lines


def _metric_charts(summary: pd.DataFrame, results_dir: Path) -> list[str]:
    plots: list[str] = []
    overall = summary[(summary["task_type"] == "ALL") & (summary["language_style"] == "ALL")]
    available = overall[overall["n_runs"] > 0]
    if available.empty:
        return plots

    os.environ.setdefault("MPLCONFIGDIR", str(results_dir / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    latency = available.dropna(subset=["p50_latency_s"])
    for provider, group in latency.groupby("provider"):
        if group.empty:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(group["model_id"], group["p50_latency_s"])
        ax.set_ylabel("Wall-clock p50 latency (seconds)")
        ax.set_title(f"Median latency by model - {provider}")
        ax.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        path = results_dir / f"latency_p50_{provider}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        plots.append(path.name)

    quality = available.dropna(subset=["quality_score"])
    for provider, group in quality.groupby("provider"):
        if group.empty:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(group["model_id"], group["quality_score"])
        ax.set_ylim(0, 1)
        ax.set_ylabel("Macro-average task score (0 to 1)")
        ax.set_title(f"Automatic quality score - {provider}")
        ax.tick_params(axis="x", rotation=25)
        fig.tight_layout()
        path = results_dir / f"quality_score_{provider}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        plots.append(path.name)
    return plots


def _suggestions(summary: pd.DataFrame) -> list[str]:
    overall = summary[(summary["task_type"] == "ALL") & (summary["language_style"] == "ALL")]
    if overall.empty or int(overall["n_success"].fillna(0).sum()) == 0:
        return ["No role suggestions yet: there are no successful model responses in raw_runs.jsonl."]
    suggestions = []
    role_metrics = [
        ("structured profile extraction", "profile_f1", "T2"),
        ("grounded answers", "grounded_fact_match", "T3"),
        ("language and multi-turn handling", "no_reask_heuristic", "T5"),
    ]
    for label, metric, task in role_metrics:
        group = summary[summary["task_type"] == task].dropna(subset=[metric]).copy()
        if group.empty:
            continue
        mean_metric = group.groupby(["model_id", "provider"], as_index=False)[metric].mean()
        winner = mean_metric.sort_values(metric, ascending=False).iloc[0]
        suggestions.append(
            f"For {label}: {winner['model_id']} ({winner['provider']}) is the current sample leader on {metric} ({_pct(winner[metric])}); treat this as a suggestion, not a final choice."
        )
    return suggestions or ["No role suggestions yet: the relevant task metrics are unavailable."]


def write_artifacts(
    *,
    raw_rows: list[dict[str, Any]],
    dataset: list[dict[str, Any]],
    models: list[ModelSpec],
    model_status: dict[str, dict[str, Any]],
    weights: dict[str, float],
    results_dir: Path,
    requested_repeats: int,
    run_metadata: dict[str, Any] | None = None,
) -> pd.DataFrame:
    results_dir.mkdir(parents=True, exist_ok=True)
    scored = score_runs(raw_rows, dataset)
    summary = build_summary(scored, models, dataset, model_status, weights)
    run_metadata = run_metadata or {}
    merged_ratings = results_dir / "human_ratings_merged.csv"
    if merged_ratings.is_file():
        ratings = pd.read_csv(merged_ratings)
        if "model_id" in ratings:
            rating_means = ratings.groupby("model_id")[["language_quality_1_5", "usefulness_1_5"]].mean()
            summary["human_language_quality_mean_1_5"] = summary["model_id"].map(rating_means["language_quality_1_5"])
            summary["human_usefulness_mean_1_5"] = summary["model_id"].map(rating_means["usefulness_1_5"])
    for column in ("human_language_quality_mean_1_5", "human_usefulness_mean_1_5"):
        if column not in summary:
            summary[column] = None
    summary_path = results_dir / "summary.csv"
    summary.to_csv(summary_path, index=False, na_rep="", float_format="%.6f")
    plots = _metric_charts(summary, results_dir)

    overall = summary[(summary["task_type"] == "ALL") & (summary["language_style"] == "ALL")]
    overall_view = overall.copy()
    for column, key in (("digest", "digest"), ("quantization", "quantization"), ("ollama_version", "ollama_version")):
        overall_view[column] = [
            (model_status.get(model_id, {}).get("model_metadata") or {}).get(key, "n/a")
            for model_id in overall_view["model_id"]
        ]
    for column in ("error_rate", "json_failure_rate", "intent_correct", "profile_f1", "not_available_correct", "citation_correct", "program_name_preserved", "no_reask_heuristic"):
        if column in overall_view:
            overall_view[column] = overall_view[column].map(_pct)
    for column in ("p50_latency_s", "p95_latency_s", "p50_ttft_s", "mean_output_tokens_per_second", "cost_usd_per_1000_requests", "quality_score", "latency_score", "cost_score", "reliability_score", "weighted_score", "human_language_quality_mean_1_5", "human_usefulness_mean_1_5"):
        if column in overall_view:
            overall_view[column] = overall_view[column].map(_fmt)
    overall_view["sample"] = overall["n_runs"].astype(int).astype(str) + " runs / " + overall["n_success"].astype(int).astype(str) + " successes"

    group_view = summary[summary["task_type"] != "ALL"].copy()
    for column in ("intent_correct", "profile_f1", "not_available_correct", "citation_correct", "grounded_fact_match", "program_name_preserved", "no_reask_heuristic", "arabic_script_detected_heuristic"):
        if column in group_view:
            group_view[column] = group_view[column].map(_pct)
    group_columns = ["model_id", "task_type", "language_style", "n_runs", "intent_correct", "profile_f1", "not_available_correct", "citation_correct", "grounded_fact_match", "program_name_preserved", "no_reask_heuristic", "arabic_script_detected_heuristic"]

    lines = [
        "# SmartCampus LLM benchmark report",
        "",
        "This report is generated from `raw_runs.jsonl` and the checked-in dataset. It makes no statistical significance claims.",
        "",
        f"Configured repeats per prompt: {requested_repeats}. Sample counts below are computed from recorded non-warm-up runs.",
        "All starter prompts are synthetic. Catalog excerpts are scraped and unverified; they are not confirmed official guidance.",
        "Tunisian Arabic and Arabizi checks require native review. T4 script detection and T5 no-repeat checks are heuristics.",
        "Local and remote latency groups must not be compared directly. Unknown remote prices remain null; local API cost excludes hardware and electricity.",
        "",
        "## Model status and overall metrics",
        "",
    ]
    lines.extend(
        _markdown_table(
            overall_view,
            ["model_id", "model_tag", "status", "digest", "quantization", "ollama_version", "sample", "error_rate", "json_failure_rate", "intent_correct", "profile_f1", "not_available_correct", "citation_correct", "p50_latency_s", "p95_latency_s", "p50_ttft_s", "mean_output_tokens_per_second", "cost_usd_per_1000_requests", "quality_score", "latency_score", "cost_score", "reliability_score", "weighted_score", "human_language_quality_mean_1_5", "human_usefulness_mean_1_5"],
            ["Model", "Tag", "Status", "Digest", "Quantization", "Ollama", "Sample", "Errors", "JSON failures", "T1 accuracy", "T2 field F1", "T3 unavailable", "T3 citation", "p50 sec", "p95 sec", "TTFT p50 sec", "Output tok/s", "API cost / 1k", "Quality", "Latency", "Cost", "Reliability", "Weighted proposal", "Human language 1-5", "Human usefulness 1-5"],
        )
    )
    lines.extend(["", "## Metrics by task and language", ""])
    if int(overall["n_runs"].fillna(0).sum()) == 0:
        lines.append("Task-level metrics will appear after at least one model is installed and returns a response. The complete task-by-language matrix is in `summary.csv`.")
    else:
        lines.extend(_markdown_table(group_view, group_columns, ["Model", "Task", "Language style", "Runs", "T1 accuracy", "T2 field F1", "T3 unavailable", "T3 citation", "T3 fact match", "T4 name kept", "T5 no re-ask*", "Arabic script*"]))
    lines.extend(["", "*Heuristic checks are labeled with an asterisk.", "", "## Automatic score definition", ""])
    weight_text = ", ".join(f"{key}={value:g}" for key, value in weights.items())
    lines.append(f"The configurable proposal weights are {weight_text}. Quality is a macro-average over available task-level metrics; latency is normalized within provider group as the group's best observed p50 divided by the model's p50; API cost is normalized within provider group; reliability is 1 minus call error rate. Missing components are omitted and remaining weights are renormalized. This score is only a comparison aid.")
    lines.extend(["", "Raw metrics remain visible above and in `summary.csv`.", ""])
    if plots:
        lines.extend(["## Charts", ""])
        for plot in plots:
            lines.append(f"![{plot}]({plot})")
        lines.append("")
    else:
        lines.extend(["## Charts", "", "No charts were generated because there are no successful timed model responses yet.", ""])
    lines.extend(["## Limitations", ""])
    if int(overall["n_success"].fillna(0).sum()) == 0:
        lines.append("No model has produced a successful benchmark response yet. Install the configured local tags before interpreting this report; no quality, speed, or cost comparison is available.")
    lines.append("The dataset is a small synthetic starter set. It is not an official admissions evaluation. Scraped catalog values and provisional codes require human review. Rule-based checks can miss paraphrases or dialect errors; manual ratings are the preferred check for language quality and usefulness.")
    machine = run_metadata.get("machine") or {}
    lines.extend(["", "## Evaluation machine and software", ""])
    if machine:
        lines.append(
            f"OS: {machine.get('os', 'unknown')}; Python: {machine.get('python', 'unknown')}; "
            f"CPU: {machine.get('cpu') or 'unknown'}; "
            f"logical CPUs: {machine.get('cpu_count') or 'unknown'}; RAM: {machine.get('ram_total_gb', 'unknown')} GB."
        )
        lines.append(
            f"GPU detection: {machine.get('gpu_detection', 'unknown')}; "
            f"GPU(s): {', '.join(machine.get('gpu_names') or []) or 'not detected'}."
        )
        versions = machine.get("library_versions") or {}
        lines.append("Library versions: " + ", ".join(f"{name} {version or 'not installed'}" for name, version in versions.items()) + ".")
    else:
        lines.append("Machine metadata is not available yet.")
    lines.extend(["", "## Pricing configuration", ""])
    for model in models:
        if model.provider == "ollama":
            lines.append(f"{model.id}: local API cost is zero; hardware and electricity are excluded.")
        else:
            lines.append(
                f"{model.id}: input price={model.input_price_per_million!r}, output price={model.output_price_per_million!r}, "
                f"source={model.pricing_source or 'unknown'}, date={model.pricing_date or 'unknown'}."
            )
    lines.extend(["", "## Which model for which role? — suggestion only", ""])
    lines.extend(_suggestions(summary))
    lines.append("The final model choice belongs to the SmartCampus team. No winner should be selected from small samples alone.")
    (results_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary
