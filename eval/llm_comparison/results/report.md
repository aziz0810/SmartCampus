# SmartCampus LLM benchmark report

This report is generated from `raw_runs.jsonl` and the checked-in dataset. It makes no statistical significance claims.

Configured repeats per prompt: 3. Sample counts below are computed from recorded non-warm-up runs.
All starter prompts are synthetic. Catalog excerpts are scraped and unverified; they are not confirmed official guidance.
Tunisian Arabic and Arabizi checks require native review. T4 script detection and T5 no-repeat checks are heuristics.
Local and remote latency groups must not be compared directly. Unknown remote prices remain null; local API cost excludes hardware and electricity.

## Model status and overall metrics

| Model | Tag | Status | Digest | Quantization | Ollama | Sample | Errors | JSON failures | T1 accuracy | T2 field F1 | T3 unavailable | T3 citation | p50 sec | p95 sec | TTFT p50 sec | Output tok/s | API cost / 1k | Quality | Latency | Cost | Reliability | Weighted proposal | Human language 1-5 | Human usefulness 1-5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| phi3 | phi3 | not_installed | n/a | n/a | n/a | 0 runs / 0 successes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemma2-2b | gemma2:2b | not_installed | n/a | n/a | n/a | 0 runs / 0 successes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| llama3.2 | llama3.2 | not_installed | n/a | n/a | n/a | 0 runs / 0 successes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| mistral | mistral | not_installed | n/a | n/a | n/a | 0 runs / 0 successes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| qwen3.5-4b | qwen3.5:4b | not_installed | n/a | n/a | n/a | 0 runs / 0 successes | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Metrics by task and language

Task-level metrics will appear after at least one model is installed and returns a response. The complete task-by-language matrix is in `summary.csv`.

*Heuristic checks are labeled with an asterisk.

## Automatic score definition

The configurable proposal weights are quality=0.4, latency=0.2, cost=0.2, reliability=0.2. Quality is a macro-average over available task-level metrics; latency is normalized within provider group as the group's best observed p50 divided by the model's p50; API cost is normalized within provider group; reliability is 1 minus call error rate. Missing components are omitted and remaining weights are renormalized. This score is only a comparison aid.

Raw metrics remain visible above and in `summary.csv`.

## Charts

No charts were generated because there are no successful timed model responses yet.

## Limitations

No model has produced a successful benchmark response yet. Install the configured local tags before interpreting this report; no quality, speed, or cost comparison is available.
The dataset is a small synthetic starter set. It is not an official admissions evaluation. Scraped catalog values and provisional codes require human review. Rule-based checks can miss paraphrases or dialect errors; manual ratings are the preferred check for language quality and usefulness.

## Evaluation machine and software

OS: Windows-11-10.0.26200-SP0; Python: 3.13.1; CPU: Intel64 Family 6 Model 154 Stepping 3, GenuineIntel; logical CPUs: 16; RAM: 15.71 GB.
GPU detection: nvidia-smi; GPU(s): NVIDIA GeForce RTX 3050 Laptop GPU.
Library versions: PyYAML 6.0.4, httpx 0.29.0, jsonschema 4.26.0, matplotlib 3.11.2, pandas 3.1.1, psutil 7.2.2, pydantic 2.14.4, pytest 9.2.0.

## Pricing configuration

phi3: local API cost is zero; hardware and electricity are excluded.
gemma2-2b: local API cost is zero; hardware and electricity are excluded.
llama3.2: local API cost is zero; hardware and electricity are excluded.
mistral: local API cost is zero; hardware and electricity are excluded.
qwen3.5-4b: local API cost is zero; hardware and electricity are excluded.

## Which model for which role? — suggestion only

No role suggestions yet: there are no successful model responses in raw_runs.jsonl.
The final model choice belongs to the SmartCampus team. No winner should be selected from small samples alone.
