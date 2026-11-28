from eval.llm_comparison.config import ModelSpec
from eval.llm_comparison.report import write_artifacts


def test_report_records_not_installed_model_without_inventing_scores(tmp_path):
    model = ModelSpec(id="phi3", provider="ollama", tag="phi3")
    dataset = [{
        "id": "t4-01", "synthetic": True, "task_type": "T4", "language_style": "fr",
        "expected": {"required_literal": "Name"},
    }]
    summary = write_artifacts(
        raw_rows=[], dataset=dataset, models=[model],
        model_status={"phi3": {"status": "not_installed", "tag": "phi3"}},
        weights={"quality": 0.4, "latency": 0.2, "cost": 0.2, "reliability": 0.2},
        results_dir=tmp_path, requested_repeats=3,
        run_metadata={"machine": {"os": "test", "python": "3.13", "library_versions": {}}},
    )
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert summary.iloc[0]["status"] == "not_installed"
    assert summary.iloc[0]["n_success"] == 0
    assert "phi3" in report and "not_installed" in report
    assert "No model has produced a successful benchmark response yet" in report
    assert "No charts were generated" in report
    assert (tmp_path / "summary.csv").is_file()

