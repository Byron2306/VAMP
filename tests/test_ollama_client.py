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
