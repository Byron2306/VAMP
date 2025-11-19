from scripts import check_ollama


def test_main_rejects_invalid_explicit_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_URL", "not a url")
    assert check_ollama.main([]) == 1


def test_main_success_with_explicit_url(monkeypatch):
    calls = []

    def _fake_probe(url, model):
        calls.append((url, model))
        return 200, "ok"

    monkeypatch.setenv("OLLAMA_API_URL", "https://example.com/api/chat")
    monkeypatch.setenv("OLLAMA_MODEL", "demo")
    monkeypatch.setattr(check_ollama, "_probe", _fake_probe)

    assert check_ollama.main([]) == 0
    assert calls == [("https://example.com/api/chat", "demo")]


def test_main_autodetect_prefers_loopback(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_URL", raising=False)
    monkeypatch.delenv("VAMP_CLOUD_API_URL", raising=False)

    calls = []

    def _fake_probe(url, model):
        calls.append(url)
        if "127.0.0.1" in url:
            return 200, "local ok"
        raise ConnectionRefusedError("offline")

    monkeypatch.setattr(check_ollama, "_probe", _fake_probe)
    assert check_ollama.main([]) == 0
    assert calls[0].startswith("http://127.0.0.1")


def test_main_records_failure_reasons(monkeypatch, capsys):
    monkeypatch.delenv("OLLAMA_API_URL", raising=False)
    monkeypatch.delenv("VAMP_CLOUD_API_URL", raising=False)

    def _fake_probe(url, model):
        raise ConnectionRefusedError(f"{url} down")

    monkeypatch.setattr(check_ollama, "_probe", _fake_probe)
    assert check_ollama.main([]) == 2
    captured = capsys.readouterr().out
    assert "Unable to reach any Ollama" in captured


def test_main_writes_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_API_URL", "https://example.com/api/chat")
    monkeypatch.setenv("OLLAMA_MODEL", "demo")
    monkeypatch.setattr(check_ollama, "_probe", lambda *_args, **_kwargs: (200, "ok"))

    env_file = tmp_path / "env.txt"
    assert check_ollama.main(["--env-file", str(env_file)]) == 0
    assert env_file.read_text().strip().splitlines() == [
        "OLLAMA_API_URL=https://example.com/api/chat",
        "OLLAMA_MODEL=demo",
    ]
