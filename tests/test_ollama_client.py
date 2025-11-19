import pytest

from backend import ollama_client


def test_coerce_json_from_sse_payload():
    raw = """data: {"choices": [{"message": {"content": "hi"}}]}"

    data: [DONE]
    """
    parsed = ollama_client._coerce_json_from_text(raw)
    assert isinstance(parsed, dict)
    assert parsed["choices"][0]["message"]["content"] == "hi"


def test_coerce_json_from_fragment_text():
    raw = 'xxx {"choices": [{"message": {"content": "fragment"}}]} trailing'
    parsed = ollama_client._coerce_json_from_text(raw)
    assert isinstance(parsed, dict)
    assert parsed["choices"][0]["message"]["content"] == "fragment"


def test_coerce_json_handles_record_separators():
    raw = "\x1e{\"response\":\"hello\",\"done\":false}\n\x1e{\"response\":\" world\",\"done\":true}\n"
    parsed = ollama_client._coerce_json_from_text(raw)
    assert isinstance(parsed, dict)
    assert parsed.get("done") is True


def test_extract_text_from_stream_chunks():
    raw = "\x1e{\"response\":\"hello\"}\n\x1e{\"message\":{\"content\":\" world\"},\"done\":true}\n"
    combined = ollama_client._extract_text_from_stream(raw)
    assert combined == "hello world"


def test_ask_ollama_uses_streaming_fallback(monkeypatch):
    class DummyResponse:
        status_code = 200
        text = 'data: {"choices": [{"message": {"content": "hello"}}]}'

        def json(self):  # pylint: disable=unused-argument
            raise ValueError("not json")

    def fake_post(*args, **kwargs):  # pylint: disable=unused-argument
        return DummyResponse()

    monkeypatch.setenv("OLLAMA_API_URL", "https://example.invalid/v1/chat/completions")
    monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:120-b")
    monkeypatch.setattr(ollama_client.requests, "post", fake_post)

    result = ollama_client.ask_ollama("hello")
    assert result == "hello"


def test_describe_brain_assets_lists_files():
    info = ollama_client.describe_brain_assets()
    assert info["asset_count"] >= 1
    assert info["system_prompt_bytes"] > 0
    assert any(asset["name"].endswith("system_nwu.txt") for asset in info["assets"])


def test_describe_ai_backend_includes_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_URL", "http://127.0.0.1:11434/api/chat")
    monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:120-b")

    info = ollama_client.describe_ai_backend()
    assert info["endpoint"]["is_ollama"] is True
    assert info["brain"]["system_prompt_bytes"] > 0
