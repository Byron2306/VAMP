#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ollama_client.py — Strict NWU Brain–aligned AI gateway for VAMP

This module provides two high-level helpers that call an OpenAI/Ollama-
compatible chat completions endpoint (e.g., Ollama, local gateway):

  • analyze_evidence_with_ollama(item, extras=None)
  • analyze_feedback_with_ollama(items, questions, rubric=None, extras=None)

Key NWU Brain integrations (no stubs, no truncation):
-----------------------------------------------------
1) Strict system prompt:
   - Loads nwu_brain/system_nwu.txt and prepends it to every request.

2) Canonical model JSON:
   - Instantiates NWUScorer using nwu_brain/brain_manifest.json.
   - For any artefact `item`, we ensure it is fully scored via SCORER.compute(...)
     then convert to canonical, compact form via SCORER.to_model_json(...).
   - The assistant receives ONLY computed, canonical fields — not raw text — so it
     cannot drift from backend policy logic.

3) Defensive JSON handling:
   - If the API returns non-JSON content (or a tool doesn’t respect response_format),
     functions fall back gracefully with a safe default object.

4) Configuration via environment:
   OLLAMA_API_URL    (default: https://cloud.ollama.ai/v1/chat/completions)
   OLLAMA_API_KEY    (required for hosted APIs; optional for local gateways)
   OLLAMA_MODEL      (default: gpt-oss:120-b)
   OLLAMA_TIMEOUT_S  (HTTP timeout; default: 120)
   VAMP_BUNDLE_LIMIT   (max items to include in feedback bundle; default: 60)

Dependencies:
  - nwu_brain.scoring.NWUScorer (part of your repo)
  - Standard library only (urllib for HTTP)

Security:
  - No secrets hardcoded. API key only read from environment.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set

import requests
import urllib.error
import urllib.request

# --------------------------------------------------------------------------------------
# Paths & bootstrap
# --------------------------------------------------------------------------------------

from functools import lru_cache
from pathlib import Path

from . import BRAIN_DATA_DIR
from .nwu_brain.scoring import NWUScorer

MANIFEST_PATH = BRAIN_DATA_DIR / "brain_manifest.json"
SYSTEM_PROMPT_PATH = BRAIN_DATA_DIR / "system_nwu.txt"

if not MANIFEST_PATH.is_file():
    raise FileNotFoundError(f"Brain manifest not found: {MANIFEST_PATH}")

SCORER = NWUScorer(str(MANIFEST_PATH))


class OllamaCallError(RuntimeError):
    """Raised when an Ollama-compatible endpoint cannot satisfy a request."""


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _render_json_file(path: Path) -> str:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return _read_text_file(path)


@lru_cache(maxsize=1)
def _brain_corpus() -> str:
    """Combine every NWU brain asset into a single, labelled corpus string."""

    sections = []

    if SYSTEM_PROMPT_PATH.exists():
        sections.append(("system_nwu.txt", _read_text_file(SYSTEM_PROMPT_PATH)))

    for path in sorted(BRAIN_DATA_DIR.glob("*")):
        if path == SYSTEM_PROMPT_PATH:
            continue
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        if suffix in {".json"}:
            rendered = _render_json_file(path)
        else:
            rendered = _read_text_file(path)

        if rendered:
            sections.append((path.name, rendered))

    if not sections:
        return "You are VAMP — use canonical NWU Brain outputs. Cite matched rules/phrases and canonical policy IDs."

    formatted = []
    for name, content in sections:
        formatted.append(f"[[[{name}]]]\n{content}".strip())

    return "\n\n".join(formatted).strip()


# Strict system prompt (fallback if file missing)
SYSTEM_PROMPT = _brain_corpus()

# --------------------------------------------------------------------------------------
# HTTP configuration
# --------------------------------------------------------------------------------------

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "https://cloud.ollama.ai/v1/chat/completions").strip()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:120-b").strip()
OLLAMA_TIMEOUT_S = int(os.getenv("OLLAMA_TIMEOUT_S", "120").strip() or "120")
VAMP_BUNDLE_LIMIT = int(os.getenv("VAMP_BUNDLE_LIMIT", "60").strip() or "60")
VAMP_REASONING_MODE = os.getenv("VAMP_REASONING_MODE", "high").strip().lower()
OLLAMA_API_KEY_HEADER = os.getenv("OLLAMA_API_KEY_HEADER", "Authorization").strip() or "Authorization"
_AUTODETECT_ENDPOINTS = (
    "http://127.0.0.1:11434/api/chat",
    "http://localhost:11434/api/chat",
)
_RESOLVED_OLLAMA_URL: Optional[str] = None


def _normalised_reasoning_mode() -> Optional[str]:
    mode = (VAMP_REASONING_MODE or "").strip().lower()
    if mode in {"", "off", "none", "disable", "disabled", "0"}:
        return None
    if mode not in {"low", "medium", "high", "max"}:
        return "high"
    return mode


def _is_ollama_endpoint(url: Optional[str]) -> bool:
    if not url:
        return False
    lowered = url.strip().lower()
    return any(token in lowered for token in ("/api/chat", "/api/generate", "ollama"))


def _reasoning_directive(model: str, url: Optional[str] = None) -> Optional[Dict[str, str]]:
    mode = _normalised_reasoning_mode()
    if not mode:
        return None
    if _is_ollama_endpoint(url):
        return None
    model_name = (model or "").lower()
    if not model_name:
        return {"effort": mode}
    # Prefer high-reasoning families but allow override for custom models
    if any(keyword in model_name for keyword in ("reason", "gpt", "ollama")):
        return {"effort": mode}
    # Unknown model families: still return directive but callers may ignore it gracefully
    return {"effort": mode}

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def _json_stream_chunks(raw: str) -> List[Any]:
    """Parse every JSON object that can be found inside an SSE/raw body."""

    if not raw:
        return []

    decoder = json.JSONDecoder()
    payloads: List[Any] = []
    idx = 0
    length = len(raw)

    while idx < length:
        char = raw[idx]

        # Skip whitespace, BOMs, record separators, and SSE metadata prefixes
        if char in " \t\r\n,":
            idx += 1
            continue
        if char in "\ufeff\x1e":
            idx += 1
            continue
        if raw.startswith("data:", idx):
            idx += len("data:")
            continue
        if raw.startswith("event:", idx):
            # Skip the rest of the line
            newline = raw.find("\n", idx)
            idx = length if newline == -1 else newline + 1
            continue
        if raw.startswith("[DONE]", idx):
            idx += len("[DONE]")
            continue
        if char not in "{[":
            idx += 1
            continue

        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            idx += 1
            continue

        payloads.append(obj)
        idx = end

    return payloads


def _select_preferred_chunk(chunks: List[Any]) -> Optional[Any]:
    """Pick the chunk that most closely resembles an LLM response."""

    def _looks_like_completion(chunk: Any) -> bool:
        if not isinstance(chunk, dict):
            return False
        if chunk.get("choices"):
            return True
        message = chunk.get("message")
        if isinstance(message, dict) and message.get("content"):
            return True
        if isinstance(chunk.get("response"), str):
            return True
        return False

    for chunk in reversed(chunks):
        if _looks_like_completion(chunk):
            return chunk

    for chunk in reversed(chunks):
        if isinstance(chunk, dict):
            return chunk

    return chunks[-1] if chunks else None


def _coerce_json_from_text(raw: str) -> Optional[Any]:
    """Best-effort JSON extraction supporting SSE/stream payloads."""

    if not raw:
        return None

    raw = raw.strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    parsed_chunks = _json_stream_chunks(raw)
    selected = _select_preferred_chunk(parsed_chunks)
    if selected is not None:
        return selected

    # As a final fallback, attempt to slice the outermost JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = raw[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass

    return None


def _extract_text_from_stream(raw: str) -> Optional[str]:
    """Combine incremental SSE payloads into a single assistant message."""

    chunks = [chunk for chunk in _json_stream_chunks(raw) if isinstance(chunk, dict)]
    if not chunks:
        return None

    parts: List[str] = []
    for chunk in chunks:
        response = chunk.get("response")
        if isinstance(response, str) and response:
            parts.append(response)
            continue

        message = chunk.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content:
                parts.append(content)
                continue

        choices = chunk.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta") or {}
                message_obj = choice.get("message") or {}
                content = delta.get("content") or message_obj.get("content")
                if isinstance(content, str) and content:
                    parts.append(content)
                    break

    combined = "".join(parts).strip()
    return combined or None


def _http_post(url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal JSON POST with SSE-aware fallback."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        parsed = _coerce_json_from_text(raw)
        if parsed is not None:
            return parsed
        # Non-JSON response — return structured error with raw body
        return {"_error": "non_json_response", "raw": raw}


def _headers() -> Dict[str, str]:
    hdrs = {"Content-Type": "application/json"}
    # API key is optional for some local gateways (e.g., no-auth reverse proxy)
    if OLLAMA_API_KEY:
        hdrs["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    return hdrs


def _ensure_scored(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the item contains canonical NWU Brain fields by running SCORER if needed.
    Returns a new dict (does not mutate the original).
    """
    if item.get("_scored"):
        return dict(item)  # already scored; shallow copy
    try:
        scored = SCORER.compute(item)
        out = dict(item)
        out.update(scored)
        out["_scored"] = True
        return out
    except Exception:
        # As a last resort, return original (caller will still try to build model JSON)
        return dict(item)


def _to_model_json(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an artefact (scored or not) to the compact, canonical model JSON
    that the assistant should see.
    """
    try:
        if not item.get("_scored"):
            item = _ensure_scored(item)
        return SCORER.to_model_json(item)
    except Exception:
        # Provide a minimal fallback that still obeys the schema keys
        return {
            "hash": item.get("hash") or "",
            "platform": item.get("platform") or item.get("source") or "",
            "title": item.get("title") or item.get("path") or "",
            "kpa": item.get("kpa") or [],
            "tier": item.get("tier") or item.get("tiers") or [],
            "score": float(item.get("score") or 0.0),
            "band": item.get("band") or "",
            "policy_flags": item.get("policy_hits") or [],
            "must_pass_risks": item.get("must_pass_risks") or [],
            "verdict": item.get("verdict") or "",
            "rationale": item.get("rationale") or "",
            "actions": item.get("actions") or [],
        }


def _build_messages(system: str, user_payload: Dict[str, Any], mode_preset: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Compose messages for the chat API. mode_preset is optional — the strict system
    prompt already encodes required behavior. You may add an extra system layer.
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    if mode_preset:
        messages.append({"role": "system", "content": mode_preset})
    messages.append({"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)})
    return messages


def _extract_json_content(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract a JSON object from a chat completions response. Returns None if not found.
    """
    try:
        choices = resp.get("choices") or []
        if not choices:
            return None
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            return None
        return json.loads(content)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------

def analyze_evidence_with_ollama(item: Dict[str, Any], extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyze a single artefact strictly against NWU Brain rules.

    Input:
      item   : dict — raw or already enriched artefact (hash, platform/source, title/path, etc.)
      extras : optional dict with additional context for the assistant (kept compact)

    Returns:
      dict with at least:
        {
          "summary": str,
          "verdict": "Exemplary|Progressing|Compliant|Review|Risk",
          "kpamap": ["KPA1", ...],
          "policies": [{"code": str, "clause": str, "reason": str}],
          "actions": [str]
        }
    """
    if not OLLAMA_API_URL:
        return {
            "summary": "(AI endpoint not configured)",
            "verdict": "Review",
            "kpamap": [],
            "policies": [],
            "actions": []
        }

    # Canonical compact object for the assistant
    model_obj = _to_model_json(_ensure_scored(item))

    # Minimal, schema-first prompt — the strict system prompt governs behavior.
    user_payload = {
        "item": model_obj,
        "extras": extras or {},
        # Gentle, explicit schema hint for tools that respect it:
        "return_schema": {
            "summary": "string",
            "verdict": "Exemplary|Progressing|Compliant|Review|Risk",
            "kpamap": ["string"],
            "policies": [{"code": "string", "clause": "string", "reason": "string"}],
            "actions": ["string"]
        }
    }

    payload = {
        "model": OLLAMA_MODEL,
        "messages": _build_messages(SYSTEM_PROMPT, user_payload),
        "temperature": 0.2,
        # Many APIs ignore this, but include if supported
        "response_format": {"type": "json_object"}
    }

    reasoning = _reasoning_directive(OLLAMA_MODEL, OLLAMA_API_URL)
    if reasoning:
        payload["reasoning"] = reasoning

    try:
        resp = _http_post(OLLAMA_API_URL, _headers(), payload)
        data = _extract_json_content(resp)
        if data is None:
            # If the provider ignored `response_format`, attempt a lenient fallback
            # returning a safe default structure.
            return {
                "summary": "(model returned non-JSON content)",
                "verdict": "Review",
                "kpamap": [],
                "policies": [],
                "actions": []
            }
        # Validate minimal keys
        return {
            "summary": str(data.get("summary", "")),
            "verdict": str(data.get("verdict", "Review")),
            "kpamap": list(data.get("kpamap", [])),
            "policies": list(data.get("policies", [])),
            "actions": list(data.get("actions", [])),
        }
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {
            "summary": f"(AI HTTP {e.code}) {detail}",
            "verdict": "Review",
            "kpamap": [],
            "policies": [],
            "actions": []
        }
    except Exception as e:
        return {
            "summary": f"(AI error) {e}",
            "verdict": "Review",
            "kpamap": [],
            "policies": [],
            "actions": []
        }


def analyze_feedback_with_ollama(
    items: List[Dict[str, Any]],
    questions: List[str],
    rubric: Optional[Dict[str, Any]] = None,
    extras: Optional[Dict[str, Any]] = None,
    mode_preset: Optional[str] = "You are a strict assessor aligned with NWU KPA and OHS guidelines. Provide detailed justification, fair bands, cite canonical policy IDs and matched phrases. Prefer concrete actions with owners and due dates."
) -> Dict[str, Any]:
    """
    Multi-question feedback over a bundle of artefacts.

    Inputs:
      items     : list of raw/enriched artefacts; each will be canonicalized via SCORER
      questions : list of user questions (e.g., "Are we compliant with OHS?")
      rubric    : optional must-pass list or scoring skeleton (kept compact)
      extras    : optional dict for additional context (e.g., user rank, targets)
      mode_preset : optional extra system layer for stricter assessor voice

    Returns:
      dict:
        {
          "answers": [
            {
              "question": str,
              "summary": str,
              "verdict": "Exemplary|Progressing|Compliant|Review|Risk",
              "scorecard": [{"hash": str, "score": number, "rationale": str}],
              "actions": [str],
              "policy_flags": [{"code": str, "clause": str, "reason": str}],
              "kpa_focus": ["KPA1","KPA2","KPA3","KPA4","KPA5"]
            }, ...
          ],
          "notes": str
        }
    """
    if not OLLAMA_API_URL:
        return {
            "answers": [{
                "question": q,
                "summary": "(AI endpoint not configured)",
                "verdict": "Review",
                "scorecard": [],
                "actions": [],
                "policy_flags": [],
                "kpa_focus": []
            } for q in questions or []],
            "notes": ""
        }

    # Canonicalize and bound the bundle size
    bundle: List[Dict[str, Any]] = []
    for it in (items or [])[: max(1, VAMP_BUNDLE_LIMIT)]:
        bundle.append(_to_model_json(_ensure_scored(it)))

    user_payload = {
        "questions": list(questions or []),
        "items": bundle,
        "rubric": rubric or {},
        "extras": extras or {},
        "return_schema": {
            "answers": [
                {
                    "question": "string",
                    "summary": "string",
                    "verdict": "Exemplary|Progressing|Compliant|Review|Risk",
                    "scorecard": [{"hash": "string", "score": "number", "rationale": "string"}],
                    "actions": ["string"],
                    "policy_flags": [{"code": "string", "clause": "string", "reason": "string"}],
                    "kpa_focus": ["string"]
                }
            ],
            "notes": "string"
        }
    }

    payload = {
        "model": OLLAMA_MODEL,
        "messages": _build_messages(SYSTEM_PROMPT, user_payload, mode_preset=mode_preset),
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    reasoning = _reasoning_directive(OLLAMA_MODEL, OLLAMA_API_URL)
    if reasoning:
        payload["reasoning"] = reasoning

    try:
        resp = _http_post(OLLAMA_API_URL, _headers(), payload)
        data = _extract_json_content(resp)
        if data is None:
            # Non-JSON content fallback
            return {
                "answers": [{
                    "question": q,
                    "summary": "(model returned non-JSON content)",
                    "verdict": "Review",
                    "scorecard": [],
                    "actions": [],
                    "policy_flags": [],
                    "kpa_focus": []
                } for q in questions or []],
                "notes": ""
            }

        # Minimal normalization
        answers = []
        for ans in data.get("answers", []):
            answers.append({
                "question": str(ans.get("question", "")),
                "summary": str(ans.get("summary", "")),
                "verdict": str(ans.get("verdict", "Review")),
                "scorecard": list(ans.get("scorecard", [])),
                "actions": list(ans.get("actions", [])),
                "policy_flags": list(ans.get("policy_flags", [])),
                "kpa_focus": list(ans.get("kpa_focus", [])),
            })

        return {"answers": answers, "notes": str(data.get("notes", ""))}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {
            "answers": [{
                "question": q,
                "summary": f"(AI HTTP {e.code}) {detail}",
                "verdict": "Review",
                "scorecard": [],
                "actions": [],
                "policy_flags": [],
                "kpa_focus": []
            } for q in questions or []],
            "notes": ""
        }
    except Exception as e:
        return {
            "answers": [{
                "question": q,
                "summary": f"(AI error) {e}",
                "verdict": "Review",
                "scorecard": [],
                "actions": [],
                "policy_flags": [],
                "kpa_focus": []
            } for q in questions or []],
            "notes": ""
        }


def _requests_headers(is_ollama: bool = False) -> Dict[str, str]:
    """Mirror _headers() but for requests-based helpers."""
    headers = {"Content-Type": "application/json"}

    env_api_key = os.environ.get("OLLAMA_API_KEY")
    api_key = (env_api_key or OLLAMA_API_KEY).strip()
    if is_ollama:
        api_key = (env_api_key or api_key).strip()

    if api_key:
        header_name = OLLAMA_API_KEY_HEADER if is_ollama else "Authorization"
        if header_name.lower() == "authorization" and not api_key.lower().startswith("bearer "):
            headers[header_name] = f"Bearer {api_key}"
        else:
            headers[header_name] = api_key

    return headers


def _format_prompt_with_system(user_prompt: str) -> str:
    """Utility for single-string LLM interfaces (e.g., Ollama /api/generate)."""
    user_prompt = (user_prompt or "").strip()
    if not SYSTEM_PROMPT:
        return user_prompt
    if not user_prompt:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\nUser:\n{user_prompt}\n\nVAMP:".strip()


def ask_ollama(prompt: str) -> str:
    """
    Lightweight helper for single-turn prompts against a Ollama-compatible endpoint.

    Unlike the higher-level helpers above this function is frequently used in scripts
    and tooling, so we keep a very small surface area while still mirroring the
    defensive behaviour (timeouts, auth headers, JSON validation) used elsewhere in
    the module.
    """

    env_url = (
        os.environ.get("OLLAMA_API_URL")
        or os.environ.get("VAMP_CLOUD_API_URL")
        or ""
    ).strip()
    default_url = OLLAMA_API_URL.strip()
    env_model = os.environ.get("OLLAMA_MODEL")
    model = (env_model or OLLAMA_MODEL or "gpt-oss:120-b").strip()

    if not env_url and not default_url:
        return "(AI endpoint not configured)"

    system_prompt = SYSTEM_PROMPT
    user_message = (prompt or "").strip()
    candidates = _candidate_api_urls(env_url, default_url)

    global _RESOLVED_OLLAMA_URL
    if not env_url and _RESOLVED_OLLAMA_URL:
        cached = _RESOLVED_OLLAMA_URL
        candidates = [cached] + [url for url in candidates if url != cached]

    errors: List[str] = []
    for url in candidates:
        try:
            text = _call_ollama_endpoint(url, model, system_prompt, user_message)
        except OllamaCallError as exc:
            errors.append(f"{url}: {exc}")
            if not env_url and _RESOLVED_OLLAMA_URL == url:
                _RESOLVED_OLLAMA_URL = None
            continue
        if not env_url:
            _RESOLVED_OLLAMA_URL = url
        return text

    if errors:
        joined = "; ".join(errors[:3])
        return f"(AI error) Unable to reach any Ollama endpoint. {joined}"
    return "(AI error) Unable to reach any Ollama endpoint."


def _candidate_api_urls(explicit_url: str, default_url: str) -> List[str]:
    """Return best-effort candidate endpoints preferring loopback before remote."""

    candidates: List[str] = []
    seen: Set[str] = set()

    def _append(url: Optional[str]) -> None:
        if not url:
            return
        trimmed = url.strip()
        if not trimmed or trimmed in seen:
            return
        seen.add(trimmed)
        candidates.append(trimmed)

    if explicit_url:
        _append(explicit_url)
        return candidates

    for url in _AUTODETECT_ENDPOINTS:
        _append(url)

    fallback_default = default_url or "https://cloud.ollama.ai/v1/chat/completions"
    _append(fallback_default)
    return candidates


def _call_ollama_endpoint(
    url: str,
    model: str,
    system_prompt: str,
    user_message: str,
) -> str:
    is_ollama_chat = "/api/chat" in url
    is_ollama_generate = "/api/generate" in url
    is_ollama = is_ollama_chat or is_ollama_generate or "ollama" in url.lower()

    effective_model = model or "gpt-oss:120-b"

    if is_ollama_generate:
        payload = {
            "model": effective_model,
            "prompt": _format_prompt_with_system(user_message),
            "stream": False,
        }
    elif is_ollama_chat:
        payload = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
        }
    else:
        payload = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
        }

    if not is_ollama:
        reasoning = _reasoning_directive(effective_model, url)
        if reasoning:
            payload["reasoning"] = reasoning

    try:
        response = requests.post(
            url,
            json=payload,
            headers=_requests_headers(is_ollama=is_ollama),
            timeout=OLLAMA_TIMEOUT_S,
        )
    except requests.RequestException as exc:  # pragma: no cover - network stack varies
        raise OllamaCallError(f"(AI error) {exc}") from exc

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("error") or body.get("message") or json.dumps(body)
            else:
                detail = json.dumps(body)
        except ValueError:
            detail = response.text.strip()
        detail = detail or "Request failed"
        raise OllamaCallError(f"(AI HTTP {response.status_code}) {detail}")

    try:
        data = response.json()
    except ValueError:
        data = _coerce_json_from_text(response.text)
        if not isinstance(data, dict):
            stream_text = _extract_text_from_stream(response.text)
            if stream_text:
                return stream_text
            raise OllamaCallError(
                f"(AI error) Invalid JSON response (status {response.status_code})"
            )

    if is_ollama_generate:
        text = data.get("response") if isinstance(data, dict) else None
        if text:
            return text
        stream_text = _extract_text_from_stream(response.text)
        if stream_text:
            return stream_text
        raise OllamaCallError("(AI error) Unexpected Ollama generate response")

    if is_ollama_chat:
        if isinstance(data, dict):
            message = data.get("message") or {}
            if isinstance(message, dict):
                text = message.get("content")
                if text:
                    return text
            # Some Ollama gateways return OpenAI-style choices
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                try:
                    return choices[0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    pass
        stream_text = _extract_text_from_stream(response.text)
        if stream_text:
            return stream_text
        raise OllamaCallError("(AI error) Unexpected Ollama chat response")

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        stream_text = _extract_text_from_stream(response.text)
        if stream_text:
            return stream_text
        raise OllamaCallError("(AI error) Unexpected response format")


@lru_cache(maxsize=1)
def _brain_asset_manifest() -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for path in sorted(BRAIN_DATA_DIR.glob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        assets.append(
            {
                "name": path.name,
                "bytes": size,
                "suffix": path.suffix or "",
            }
        )
    return assets


def describe_brain_assets() -> Dict[str, Any]:
    """Return metadata showing which NWU Brain files seed the system prompt."""

    assets = _brain_asset_manifest()
    return {
        "manifest_path": str(MANIFEST_PATH),
        "system_prompt_path": str(SYSTEM_PROMPT_PATH),
        "system_prompt_bytes": len(SYSTEM_PROMPT.encode("utf-8")) if SYSTEM_PROMPT else 0,
        "system_prompt_preview": SYSTEM_PROMPT[:400],
        "asset_count": len(assets),
        "assets": assets,
    }


def describe_ai_backend() -> Dict[str, Any]:
    """Expose resolved Ollama endpoint + NWU Brain metadata for diagnostics."""

    resolved_url = (os.environ.get("OLLAMA_API_URL") or OLLAMA_API_URL).strip()
    resolved_model = (os.environ.get("OLLAMA_MODEL") or OLLAMA_MODEL).strip()

    return {
        "endpoint": {
            "url": resolved_url,
            "model": resolved_model,
            "timeout_s": OLLAMA_TIMEOUT_S,
            "is_ollama": _is_ollama_endpoint(resolved_url),
            "reasoning_mode": _normalised_reasoning_mode(),
            "reasoning_directive": _reasoning_directive(resolved_model, resolved_url),
        },
        "brain": describe_brain_assets(),
    }
