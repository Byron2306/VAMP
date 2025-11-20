"""Utility script to verify (and auto-detect) the Ollama endpoint before launch."""
from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


DEFAULT_TIMEOUT = float(os.getenv("OLLAMA_HEALTH_TIMEOUT", "5"))


@dataclass(frozen=True)
class EndpointCandidate:
    url: str
    model: str
    source: str


def _probe(url: str, model: str) -> Tuple[int, str]:
    payload = {
        "model": model or "gpt-oss:120-b",
        "messages": [{"role": "user", "content": "health-check"}],
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    context = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT, context=context) as resp:  # noqa: S310
        body = resp.read(256)
        return resp.status, body.decode("utf-8", errors="replace")


def _normalise_url(url: str) -> str:
    if any(ch.isspace() for ch in url):
        raise ValueError(f"Invalid Ollama endpoint URL: {url!r}")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    if not parsed.scheme and parsed.path:
        # Allow bare hosts (e.g., 127.0.0.1:11434/api/chat)
        return _normalise_url(f"http://{url}")
    raise ValueError(f"Invalid Ollama endpoint URL: {url!r}")


def _candidate_endpoints(explicit_url: str, model: str) -> List[EndpointCandidate]:
    """Return candidate endpoints (explicit override → loopback defaults)."""

    canonical_model = model or "gpt-oss:120-b"
    candidates: List[EndpointCandidate] = []

    def _append(url: Optional[str], source: str) -> None:
        if not url:
            return
        trimmed = url.strip()
        if not trimmed:
            return
        try:
            canonical = _normalise_url(trimmed)
        except ValueError:
            return
        if any(candidate.url == canonical for candidate in candidates):
            return
        candidates.append(EndpointCandidate(canonical, canonical_model, source))

    if explicit_url:
        _append(explicit_url, "configured")
        return candidates

    for loopback in ("http://127.0.0.1:11434/api/chat", "http://localhost:11434/api/chat"):
        _append(loopback, "local Ollama (loopback)")

    return candidates


def _write_env_file(env_file: str, url: str, model: str) -> None:
    path = Path(env_file)
    path.write_text(f"OLLAMA_API_URL={url}\nOLLAMA_MODEL={model}\n", encoding="utf-8")


def _interpret_probe(url: str, model: str) -> Tuple[Optional[int], str, Optional[str]]:
    """Return (status, snippet, error_message) for a candidate probe."""

    try:
        status, snippet = _probe(url, model)
        return status, snippet, None
    except urllib.error.HTTPError as exc:
        snippet = exc.read().decode("utf-8", errors="replace")
        if 400 <= exc.code < 500:
            return exc.code, snippet, None
        return None, snippet, f"HTTP {exc.code}: {snippet[:200]}"
    except Exception as exc:  # pragma: no cover - network failure paths
        return None, "", str(exc)


def _select_endpoint(candidates: Iterable[EndpointCandidate]) -> Tuple[Optional[EndpointCandidate], Optional[int], str, List[str]]:
    errors: List[str] = []
    for candidate in candidates:
        print(f"[check_ollama] Probing {candidate.url} ({candidate.source}) ...")
        status, snippet, error = _interpret_probe(candidate.url, candidate.model)
        if error:
            errors.append(f"{candidate.url}: {error}")
            continue
        return candidate, status, snippet, errors
    return None, None, "", errors


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check connectivity to an Ollama-compatible endpoint")
    parser.add_argument(
        "--env-file",
        help="Optional path to write OLLAMA_API_URL/OLLAMA_MODEL assignments for callers",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    explicit_url = (os.getenv("OLLAMA_API_URL") or "").strip()
    model = (os.getenv("OLLAMA_MODEL") or "").strip()

    if explicit_url:
        try:
            _normalise_url(explicit_url)
        except ValueError as exc:
            print(f"[check_ollama] ERROR: {exc}")
            return 1

    candidates = _candidate_endpoints(explicit_url, model)
    if not candidates:
        print("[check_ollama] ERROR: No endpoint candidates found.")
        return 1

    candidate, status, snippet, errors = _select_endpoint(candidates)
    if not candidate or status is None:
        print("[check_ollama] ERROR: Unable to reach any Ollama endpoint candidates.")
        for error in errors:
            print("    -", error)
        return 2

    print(
        "[check_ollama] SUCCESS:",
        f"source={candidate.source}",
        f"status={status}",
        ("body=" + snippet[:120].replace("\n", " ").strip()),
    )

    if args.env_file:
        try:
            _write_env_file(args.env_file, candidate.url, candidate.model)
        except OSError as exc:
            print(f"[check_ollama] WARNING: Unable to write env file {args.env_file!r}: {exc}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
