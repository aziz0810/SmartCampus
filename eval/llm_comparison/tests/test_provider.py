import json

import httpx

from eval.llm_comparison.providers.ollama import ModelUnavailable, OllamaProvider


def test_ollama_stream_captures_text_usage_and_timings():
    events = [
        {"message": {"role": "assistant", "content": "Salut"}, "done": False},
        {
            "message": {"role": "assistant", "content": "."},
            "done": True,
            "total_duration": 100_000_000,
            "load_duration": 10_000_000,
            "prompt_eval_count": 12,
            "prompt_eval_duration": 20_000_000,
            "eval_count": 3,
            "eval_duration": 50_000_000,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = b"".join(json.dumps(event).encode() + b"\n" for event in events)
        return httpx.Response(200, content=payload, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://localhost:11434", client=client)
    try:
        result = provider.chat(
            "phi3",
            [{"role": "user", "content": "Bonjour"}],
            {"temperature": 0, "seed": 42, "max_output_tokens": 32},
        )
    finally:
        provider.close()

    assert result.error is None
    assert result.text == "Salut."
    assert result.usage == {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    assert result.timings["total_duration_s"] == 0.1
    assert result.timings["load_duration_s"] == 0.01
    assert result.timings["output_tokens_per_second"] == 60
    assert result.timings["ttft_s"] is not None


def test_ollama_timeout_is_returned_as_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://localhost:11434", client=client)
    try:
        result = provider.chat("phi3", [{"role": "user", "content": "test"}], {"temperature": 0, "max_output_tokens": 8})
    finally:
        provider.close()
    assert result.error == {"type": "timeout", "message": "ReadTimeout"}


def test_inspect_model_uses_server_reported_tag_digest_and_quantization():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.18"}, request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "phi3:latest", "digest": "abc", "size": 123}]}, request=request)
        return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M", "parameter_size": "3.8B", "family": "phi3"}}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://localhost:11434", client=client)
    try:
        metadata = provider.inspect_model("phi3")
    finally:
        provider.close()
    assert metadata["installed_tag"] == "phi3:latest"
    assert metadata["digest"] == "abc"
    assert metadata["quantization"] == "Q4_K_M"
    assert metadata["ollama_version"] == "0.40.18"


def test_inspect_model_rejects_uninstalled_tag():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.18"}, request=request)
        return httpx.Response(200, json={"models": []}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OllamaProvider("http://localhost:11434", client=client)
    try:
        try:
            provider.inspect_model("missing-tag")
        except ModelUnavailable as exc:
            assert "missing-tag" in str(exc)
        else:
            raise AssertionError("Expected ModelUnavailable")
    finally:
        provider.close()
