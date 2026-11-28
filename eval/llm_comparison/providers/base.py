from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None


class Provider(ABC):
    @abstractmethod
    def chat(self, model_tag: str, messages: list[dict[str, str]], params: dict[str, Any]) -> ProviderResult:
        """Run one chat call and return output, usage, timings, and any error."""

    @abstractmethod
    def inspect_model(self, model_tag: str) -> dict[str, Any]:
        """Return provider-reported metadata for an installed model tag."""

    @abstractmethod
    def close(self) -> None:
        """Release provider resources."""
