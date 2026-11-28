# SmartCampus LLM comparison

This benchmark compares local Ollama models on a fixed set of synthetic
orientation-assistant tasks. Catalog excerpts come from
`backend/seed/iit_scraped_catalog.json`; the scrape is unverified, and excerpts
are explicitly labeled as synthetic benchmark context rather than confirmed
official guidance. Tunisian Arabic and Arabizi rows require native review.

## Install and build the starter dataset

Use Python 3.12 and install the isolated benchmark requirements:

```powershell
py -3.12 -m venv .venv-llm
.\.venv-llm\Scripts\Activate.ps1
python -m pip install -r eval/llm_comparison/requirements.txt
python -m dataset.build_starter
```

The checked-in model list is in `models.yaml`. It includes the requested
`phi3`, `gemma2:2b`, `llama3.2`, and `mistral` tags, plus `qwen3.5:4b` as an
Apache-2.0 candidate. The model specs, exact tag, digest, and quantization are
recorded from the running Ollama server at benchmark time. No weights are
downloaded automatically. Install a tag with `ollama pull <tag>` before running
it; Ollama must be reachable at `OLLAMA_BASE_URL` (default
`http://localhost:11434`).

## Run

From the repository root:

```powershell
python -m eval.llm_comparison.run --models models.yaml --dataset dataset/starter_prompts.jsonl --limit-prompts 3 --model phi3
```

The path resolver accepts paths relative to the repository root or this
directory. Remove `--limit-prompts 3 --model phi3` to run the selected dataset
on all enabled models. Defaults are three sequential repeats, temperature 0,
seed 42 where supported, 512 max output tokens, and a 120-second timeout. Each
local model receives one recorded warm-up excluded from summary metrics. The
runner never downloads models and never logs API keys.

Missing tags are recorded as `not_installed` in `results/run_metadata.json`;
the report will not fabricate model responses or scores. Reruns resume from
completed `(model, prompt, repeat)` rows in `results/raw_runs.jsonl`.

## Outputs and review

- `results/raw_runs.jsonl`: every warm-up and call, including failed calls.
- `results/summary.csv`: metrics by model, task, and language style.
- `results/report.md`: raw metrics, proposal score, limitations, charts, and
  role suggestions. It makes no significance claims.
- `results/human_review_blind.csv`: shuffled sample with model IDs hidden.
- `results/human_review_key.json`: local key used to merge ratings; ignored by
  Git. Do not give this file to blind raters.

Fill the two 1-5 rating columns, then merge the ratings:

```powershell
python -m eval.llm_comparison.run --merge-human eval/llm_comparison/results/human_review_blind.csv
```

See `human_rating_rubric.md` for the short rating guide. Human scores are
reported separately and are not part of the default weighted score. The
optional LLM judge is off.

## Scoring notes

T1 is exact intent-label accuracy. T2 reports strict JSON validity, schema
validity, and field-level precision/recall/F1; non-null values where the gold
profile is null count as invented-value false positives. T3 reports correct
unavailable answers, exact source-ID citations for answerable items, required
fact presence, and a rule-based injection check. T4 exact-name preservation
and Arabic-script detection, and T5 fact recall/no-reask checks, are labeled
heuristics. Cost is null for remote providers until a verified price, source,
and date are configured; local API cost is zero, excluding hardware and power.

Latency and weighted scores are normalized only within provider type. Local
hardware latency is not compared directly to remote network latency. Meta
support is deferred until its official endpoint, authentication, model IDs, and
price details are supplied or verified from official documentation.
