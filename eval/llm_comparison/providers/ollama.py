from __future__ import annotations

import json
import time
from typing import Any

import httpx

from eval.llm_comparison.providers.base import Provider, ProviderResult


class ModelUnavailable(RuntimeError):
    pass


class OllamaProvider(Provider):
    def __init__(self, base_url: str, timeout_seconds: float = 120, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
        )
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def server_version(self) -> str:
        response = self.client.get(f"{self.base_url}/api/version")
        response.raise_for_status()
        return str(response.json().get("version", "unknown"))

    def inspect_model(self, model_tag: str) -> dict[str, Any]:
        version = self.server_version()
        response = self.client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        exact = [entry for entry in models if entry.get("name") == model_tag]
        aliases = [entry for entry in models if entry.get("name", "").removesuffix(":latest") == model_tag]
        match = (exact or aliases or [None])[0]
        if match is None:
            raise ModelUnavailable(f"Ollama tag is not installed: {model_tag}")

        show_response = self.client.post(f"{self.base_url}/api/show", json={"model": match["name"]})
        show_response.raise_for_status()
        show = show_response.json()
        details = show.get("details", {})
        return {
            "provider": "ollama",
            "configured_tag": model_tag,
            "installed_tag": match.get("name"),
            "digest": match.get("digest"),
            "size_bytes": match.get("size"),
            "quantization": details.get("quantization_level"),
            "parameter_size": details.get("parameter_size"),
            "family": details.get("family"),
            "ollama_version": version,
        }

    def chat(self, model_tag: str, messages: list[dict[str, str]], params: dict[str, Any]) -> ProviderResult:
        request_body = {
            "model": model_tag,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": params["temperature"],
                "num_predict": params["max_output_tokens"],
            },
        }
        if params.get("seed") is not None:
            request_body["options"]["seed"] = params["seed"]

        started = time.perf_counter()
        first_token_at: float | None = None
        chunks: list[str] = []
        final: dict[str, Any] = {}
        try:
            with self.client.stream("POST", f"{self.base_url}/api/chat", json=request_body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        return ProviderResult(error={"type": "invalid_stream_json", "message": str(exc)})
                    if event.get("error"):
                        return ProviderResult(error={"type": "ollama_error", "message": str(event["error"])})
                    content = event.get("message", {}).get("content", "")
                    if content:
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        chunks.append(content)
                    if event.get("done"):
                        final = event
        except httpx.TimeoutException as exc:
            return ProviderResult(error={"type": "timeout", "message": type(exc).__name__})
        except httpx.HTTPStatusError as exc:
            return ProviderResult(
                error={"type": "http_error", "status_code": exc.response.status_code, "message": "Ollama returned an HTTP error"}
            )
        except httpx.HTTPError as exc:
            return ProviderResult(error={"type": "connection_error", "message": type(exc).__name__})

        wall_seconds = time.perf_counter() - started
        if not final:
            return ProviderResult(
                text="".join(chunks),
                timings={"wall_latency_s": wall_seconds, "ttft_s": first_token_at - started if first_token_at else None},
                error={"type": "incomplete_stream", "message": "Ollama stream ended without a done event"},
            )

        def seconds(key: str) -> float | None:
            value = final.get(key)
            return value / 1_000_000_000 if isinstance(value, (int, float)) else None

        eval_duration_s = seconds("eval_duration")
        eval_count = final.get("eval_count")
        token_rate = eval_count / eval_duration_s if eval_count and eval_duration_s else None
        return ProviderResult(
            text="".join(chunks),
            usage={
                "prompt_tokens": final.get("prompt_eval_count"),
                "completion_tokens": eval_count,
                "total_tokens": (final.get("prompt_eval_count") or 0) + (eval_count or 0),
            },
            timings={
                "wall_latency_s": wall_seconds,
                "ttft_s": first_token_at - started if first_token_at else None,
                "total_duration_s": seconds("total_duration"),
                "load_duration_s": seconds("load_duration"),
                "prompt_eval_duration_s": seconds("prompt_eval_duration"),
                "eval_duration_s": eval_duration_s,
                "output_tokens_per_second": token_rate,
                "ollama_raw_ns": {
                    key: final.get(key)
                    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
                },
            },
        )
