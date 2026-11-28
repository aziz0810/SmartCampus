from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_MODELS_FILE = PACKAGE_ROOT / "models.yaml"
DEFAULT_DATASET_FILE = PACKAGE_ROOT / "dataset" / "starter_prompts.jsonl"
DEFAULT_RESULTS_DIR = PACKAGE_ROOT / "results"


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    provider: Literal["ollama", "meta"]
    tag: str
    enabled: bool = True
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    pricing_source: str | None = None
    pricing_date: str | None = None


class BenchmarkSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeats: int = Field(default=3, ge=1)
    temperature: float = Field(default=0.0, ge=0.0)
    seed: int | None = 42
    max_output_tokens: int = Field(default=512, ge=1)
    timeout_seconds: float = Field(default=120.0, gt=0)
    ollama_base_url: str = "http://localhost:11434"
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "quality": 0.4,
            "latency": 0.2,
            "cost": 0.2,
            "reliability": 0.2,
        }
    )
    human_sample_per_language: int = Field(default=5, ge=1)
    random_seed: int = 42


class ModelsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark: BenchmarkSettings
    models: list[ModelSpec]


def load_models_file(path: Path = DEFAULT_MODELS_FILE) -> ModelsFile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = ModelsFile.model_validate(raw)
    if len({model.id for model in config.models}) != len(config.models):
        raise ValueError("Model ids in models.yaml must be unique")
    base_url = os.getenv("OLLAMA_BASE_URL")
    if base_url:
        config.benchmark.ollama_base_url = base_url.rstrip("/")
    else:
        config.benchmark.ollama_base_url = config.benchmark.ollama_base_url.rstrip("/")
    if not config.benchmark.weights or any(value < 0 for value in config.benchmark.weights.values()):
        raise ValueError("Score weights must be present and non-negative")
    return config


def resolve_input_path(path: Path, base_dir: Path = PACKAGE_ROOT) -> Path:
    if path.is_absolute() and path.exists():
        return path
    if path.exists():
        return path.resolve()
    candidate = base_dir / path
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(f"Input file not found: {path}")
