from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from eval.llm_comparison.config import (
    DEFAULT_DATASET_FILE,
    DEFAULT_MODELS_FILE,
    DEFAULT_RESULTS_DIR,
    PACKAGE_ROOT,
    load_models_file,
    resolve_input_path,
)
from eval.llm_comparison.dataset.loader import load_jsonl
from eval.llm_comparison.providers.base import ProviderResult
from eval.llm_comparison.providers.ollama import ModelUnavailable, OllamaProvider

PROMPT_VERSION = "v1"
SYSTEM_PROMPT_PATH = PACKAGE_ROOT / "prompts" / PROMPT_VERSION / "system.txt"
USER_TEMPLATE_PATH = PACKAGE_ROOT / "prompts" / PROMPT_VERSION / "user_template.txt"
VERSIONED_LIBRARIES = ("httpx", "pydantic", "PyYAML", "jsonschema", "pandas", "matplotlib", "pytest", "psutil")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def machine_metadata() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    gpu_names = None
    gpu_detection = "nvidia-smi unavailable; GPU model not detected"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        gpu_names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        gpu_detection = "nvidia-smi"
    except (OSError, subprocess.SubprocessError):
        pass
    versions = {}
    for library in VERSIONED_LIBRARIES:
        try:
            versions[library] = importlib.metadata.version(library)
        except importlib.metadata.PackageNotFoundError:
            versions[library] = None
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "ram_total_gb": round(memory.total / 1024**3, 2),
        "ram_available_gb_at_start_gb": round(memory.available / 1024**3, 2),
        "gpu_names": gpu_names,
        "gpu_detection": gpu_detection,
        "library_versions": versions,
    }


def _format_context(context: dict[str, Any]) -> str:
    sources = context.get("sources", [])
    if not sources and not context.get("injected_text"):
        return "Context: none supplied.\n"
    lines = [
        "Context label: SYNTHETIC BENCHMARK EXCERPT. Any catalog-derived value is unverified and is not confirmed official guidance.",
    ]
    for source in sources:
        lines.append(f"[{source['id']}] exact catalog title: {source['title']}")
        if source.get("source_url"):
            lines.append(f"[{source['id']}] source URL: {source['source_url']}")
    if context.get("injected_text"):
        lines.append(f"[UNTRUSTED TEXT EMBEDDED IN THE EXCERPT: {context['injected_text']}]")
    return "\n".join(lines) + "\n"


def build_messages(item: dict[str, Any], system_prompt: str, user_template: str) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": system_prompt}]
    for history_message in item.get("history", []):
        role = history_message.get("role")
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported conversation role in {item['id']}: {role}")
        messages.append({"role": role, "content": history_message["content"]})
    user_content = user_template.format(
        task_type=item["task_type"],
        language_style=item["language_style"],
        task_instruction=item["task_instruction"],
        context_block=_format_context(item.get("context", {})),
        prompt=item["prompt"],
    )
    messages.append({"role": "user", "content": user_content})
    return messages


def _read_raw(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid raw run JSONL at {path}:{line_number}") from exc
    return rows


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _model_signature(model_meta: dict[str, Any] | None, model_tag: str) -> str:
    return _sha256_bytes(
        json.dumps({"tag": model_tag, "metadata": model_meta}, sort_keys=True).encode("utf-8")
    )


def _load_run_metadata(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("runs"), list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema_version": 1, "runs": []}


def _write_run_metadata(path: Path, entry: dict[str, Any]) -> None:
    data = _load_run_metadata(path)
    data["runs"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _completed_keys(
    raw_rows: list[dict[str, Any]], dataset_hash: str, prompt_hash: str, params: dict[str, Any]
) -> set[tuple[str, str, int, str]]:
    params_hash = _sha256_bytes(json.dumps(params, sort_keys=True).encode("utf-8"))
    return {
        (row["model_id"], row["prompt_id"], row["repeat"], row["model_signature"])
        for row in raw_rows
        if not row.get("is_warmup")
        and row.get("dataset_hash") == dataset_hash
        and row.get("prompt_hash") == prompt_hash
        and row.get("params_hash") == params_hash
        and isinstance(row.get("repeat"), int)
        and row.get("model_signature")
    }


def _safe_chat(provider: OllamaProvider, model_tag: str, messages: list[dict[str, str]], params: dict[str, Any]) -> ProviderResult:
    try:
        return provider.chat(model_tag, messages, params)
    except Exception as exc:
        return ProviderResult(error={"type": "provider_exception", "message": type(exc).__name__})


def _record(
    *,
    run_id: str,
    model_id: str,
    model_tag: str,
    model_metadata: dict[str, Any],
    model_signature: str,
    dataset_hash: str,
    prompt_hash: str,
    params_hash: str,
    params: dict[str, Any],
    result: ProviderResult,
    prompt_id: str,
    task_type: str,
    language_style: str,
    repeat: int | None,
    messages: list[dict[str, str]],
    is_warmup: bool = False,
) -> dict[str, Any]:
    error = result.error
    if error is None and not result.text.strip():
        error = {"type": "empty_output", "message": "Provider returned an empty response"}
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "prompt_version": PROMPT_VERSION,
        "model_id": model_id,
        "model_tag": model_tag,
        "model_signature": model_signature,
        "model_metadata": model_metadata,
        "provider": "ollama",
        "prompt_id": prompt_id,
        "task_type": task_type,
        "language_style": language_style,
        "repeat": repeat,
        "is_warmup": is_warmup,
        "synthetic_prompt": True,
        "needs_native_review": False,
        "dataset_hash": dataset_hash,
        "prompt_hash": prompt_hash,
        "params_hash": params_hash,
        "params": params,
        "messages": messages,
        "response": result.text,
        "usage": result.usage,
        "timings": result.timings,
        "cost_usd": 0.0,
        "error": error,
    }


def run_benchmark(
    *,
    models_path: Path = DEFAULT_MODELS_FILE,
    dataset_path: Path = DEFAULT_DATASET_FILE,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    repeats: int | None = None,
    limit_prompts: int | None = None,
    model_ids: set[str] | None = None,
) -> dict[str, Any]:
    models_path = resolve_input_path(models_path)
    dataset_path = resolve_input_path(dataset_path)
    config = load_models_file(models_path)
    enabled_models = [model for model in config.models if model.enabled and (model_ids is None or model.id in model_ids)]
    if model_ids:
        known = {model.id for model in config.models}
        unknown = model_ids - known
        disabled = model_ids - {model.id for model in enabled_models}
        if unknown:
            raise ValueError(f"Unknown model ids: {', '.join(sorted(unknown))}")
        if disabled:
            raise ValueError(f"Models are disabled in models.yaml: {', '.join(sorted(disabled))}")
    dataset = load_jsonl(dataset_path)
    if limit_prompts is not None:
        if limit_prompts < 1:
            raise ValueError("--limit-prompts must be positive")
        dataset = dataset[:limit_prompts]

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    user_template = USER_TEMPLATE_PATH.read_text(encoding="utf-8")
    dataset_hash = _sha256_bytes(dataset_path.read_bytes())
    prompt_hash = _sha256_bytes((system_prompt + "\n" + user_template).encode("utf-8"))
    count = config.benchmark.repeats if repeats is None else repeats
    if count < 1:
        raise ValueError("Repeats must be positive")
    params = {
        "temperature": config.benchmark.temperature,
        "seed": config.benchmark.seed,
        "max_output_tokens": config.benchmark.max_output_tokens,
        "timeout_seconds": config.benchmark.timeout_seconds,
    }
    params_hash = _sha256_bytes(json.dumps(params, sort_keys=True).encode("utf-8"))
    raw_path = results_dir / "raw_runs.jsonl"
    metadata_path = results_dir / "run_metadata.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.touch(exist_ok=True)
    raw_rows = _read_raw(raw_path)
    completed = _completed_keys(raw_rows, dataset_hash, prompt_hash, params)
    run_id = str(uuid.uuid4())
    statuses: dict[str, dict[str, Any]] = {}
    machine = machine_metadata()

    for model in enabled_models:
        if model.provider != "ollama":
            statuses[model.id] = {"status": "deferred", "reason": "Meta adapter awaits official endpoint/auth details"}
            continue
        provider = OllamaProvider(config.benchmark.ollama_base_url, config.benchmark.timeout_seconds)
        try:
            model_meta = provider.inspect_model(model.tag)
        except ModelUnavailable as exc:
            statuses[model.id] = {"status": "not_installed", "tag": model.tag, "reason": str(exc)}
            provider.close()
            continue
        except Exception as exc:
            statuses[model.id] = {"status": "preflight_error", "tag": model.tag, "reason": type(exc).__name__}
            provider.close()
            continue

        signature = _model_signature(model_meta, model.tag)
        statuses[model.id] = {
            "status": "ready",
            "tag": model.tag,
            "model_signature": signature,
            "model_metadata": model_meta,
        }
        warmup_exists = any(
            row.get("model_id") == model.id
            and row.get("model_signature") == signature
            and row.get("is_warmup")
            and row.get("prompt_hash") == prompt_hash
            and row.get("params_hash") == params_hash
            for row in raw_rows
        )
        if not warmup_exists:
            warmup_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Warm-up only. Reply with exactly: OK"},
            ]
            result = _safe_chat(provider, model.tag, warmup_messages, params)
            warmup_record = _record(
                run_id=run_id,
                model_id=model.id,
                model_tag=model.tag,
                model_metadata=model_meta,
                model_signature=signature,
                dataset_hash=dataset_hash,
                prompt_hash=prompt_hash,
                params_hash=params_hash,
                params=params,
                result=result,
                prompt_id="__warmup__",
                task_type="warmup",
                language_style="fr",
                repeat=None,
                messages=warmup_messages,
                is_warmup=True,
            )
            _append_jsonl(raw_path, warmup_record)
            raw_rows.append(warmup_record)

        for item in dataset:
            for repeat_index in range(1, count + 1):
                key = (model.id, item["id"], repeat_index, signature)
                if key in completed:
                    continue
                messages = build_messages(item, system_prompt, user_template)
                result = _safe_chat(provider, model.tag, messages, params)
                record = _record(
                    run_id=run_id,
                    model_id=model.id,
                    model_tag=model.tag,
                    model_metadata=model_meta,
                    model_signature=signature,
                    dataset_hash=dataset_hash,
                    prompt_hash=prompt_hash,
                    params_hash=params_hash,
                    params=params,
                    result=result,
                    prompt_id=item["id"],
                    task_type=item["task_type"],
                    language_style=item["language_style"],
                    repeat=repeat_index,
                    messages=messages,
                )
                record["needs_native_review"] = item.get("needs_native_review", False)
                _append_jsonl(raw_path, record)
                raw_rows.append(record)
                completed.add(key)
        provider.close()

    metadata_entry = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path),
        "dataset_hash": dataset_hash,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
        "requested_repeats": count,
        "requested_prompt_count": len(dataset),
        "params": params,
        "machine": machine,
        "model_status": statuses,
    }
    _write_run_metadata(metadata_path, metadata_entry)
    return {
        "run_id": run_id,
        "raw_path": raw_path,
        "metadata_path": metadata_path,
        "model_status": statuses,
        "raw_rows": raw_rows,
        "dataset_hash": dataset_hash,
        "prompt_hash": prompt_hash,
        "params_hash": params_hash,
        "prompt_ids": {item["id"] for item in dataset},
        "repeats": count,
    }
