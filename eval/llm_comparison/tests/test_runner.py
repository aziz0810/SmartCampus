import json

from eval.llm_comparison import runner
from eval.llm_comparison.providers.base import ProviderResult


class FakeProvider:
    calls = 0

    def __init__(self, base_url, timeout_seconds):
        self.closed = False

    def inspect_model(self, model_tag):
        return {"provider": "ollama", "installed_tag": model_tag, "digest": "fake"}

    def chat(self, model_tag, messages, params):
        type(self).calls += 1
        return ProviderResult(text="test response", timings={"wall_latency_s": 0.1})

    def close(self):
        self.closed = True


def test_runner_records_warmup_and_resumes_completed_calls(tmp_path, monkeypatch):
    model_path = tmp_path / "models.yaml"
    model_path.write_text(
        "benchmark:\n  repeats: 2\n  temperature: 0\n  seed: 42\n  max_output_tokens: 32\n"
        "  timeout_seconds: 3\n  ollama_base_url: http://localhost:11434\n"
        "  weights: {quality: 0.4, latency: 0.2, cost: 0.2, reliability: 0.2}\n"
        "models:\n  - id: fake\n    provider: ollama\n    tag: fake:latest\n    enabled: true\n",
        encoding="utf-8",
    )
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps({
            "id": "t4-01", "synthetic": True, "task_type": "T4", "language_style": "fr",
            "prompt": "Keep this name", "task_instruction": "Preserve it.",
            "context": {"sources": [], "injected_text": None}, "expected": {"required_literal": "Name"},
        }) + "\n",
        encoding="utf-8",
    )
    system_path = tmp_path / "system.txt"
    template_path = tmp_path / "template.txt"
    system_path.write_text("System", encoding="utf-8")
    template_path.write_text("{task_type} {language_style} {task_instruction}\n{context_block}{prompt}", encoding="utf-8")

    FakeProvider.calls = 0
    monkeypatch.setattr(runner, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(runner, "machine_metadata", lambda: {"os": "test", "library_versions": {}})
    monkeypatch.setattr(runner, "SYSTEM_PROMPT_PATH", system_path)
    monkeypatch.setattr(runner, "USER_TEMPLATE_PATH", template_path)

    first = runner.run_benchmark(models_path=model_path, dataset_path=dataset_path, results_dir=tmp_path / "results")
    assert len(first["raw_rows"]) == 3
    assert sum(row["is_warmup"] for row in first["raw_rows"]) == 1
    assert FakeProvider.calls == 3

    second = runner.run_benchmark(models_path=model_path, dataset_path=dataset_path, results_dir=tmp_path / "results")
    assert len(second["raw_rows"]) == 3
    assert FakeProvider.calls == 3



def test_format_context_shows_optional_source_text():
    with_text = runner._format_context(
        {"sources": [{"id": "S1", "title": "Titre", "text": "Extrait officiel."}]}
    )
    assert "[S1] excerpt: Extrait officiel." in with_text

    title_only = runner._format_context({"sources": [{"id": "S1", "title": "Titre"}]})
    assert "excerpt" not in title_only
