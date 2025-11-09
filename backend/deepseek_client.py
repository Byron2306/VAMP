#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deepseek_client.py — Strict NWU Brain–aligned AI gateway for VAMP

This module provides two high-level helpers that call an OpenAI/Ollama-
compatible chat completions endpoint (e.g., DeepSeek, local gateway):

  • analyze_evidence_with_deepseek(item, extras=None)
  • analyze_feedback_with_deepseek(items, questions, rubric=None, extras=None)

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
   DEEPSEEK_API_URL    (default: https://api.deepseek.com/v1/chat/completions)
   DEEPSEEK_API_KEY    (required for hosted APIs; optional for local gateways)
   DEEPSEEK_MODEL      (e.g., deepseek-reasoner, deepseek-chat; default: deepseek-reasoner)
   DEEPSEEK_TIMEOUT_S  (HTTP timeout; default: 120)
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
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error

# --------------------------------------------------------------------------------------
# Paths & bootstrap
# --------------------------------------------------------------------------------------

from . import BRAIN_DATA_DIR
from .nwu_brain.scoring import NWUScorer

MANIFEST_PATH = BRAIN_DATA_DIR / "brain_manifest.json"
SYSTEM_PROMPT_PATH = BRAIN_DATA_DIR / "system_nwu.txt"

if not MANIFEST_PATH.is_file():
    raise FileNotFoundError(f"Brain manifest not found: {MANIFEST_PATH}")

SCORER = NWUScorer(str(MANIFEST_PATH))

# Strict system prompt (fallback if file missing)
SYSTEM_PROMPT = (
    SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if SYSTEM_PROMPT_PATH.exists()
    else "You are VAMP — use canonical NWU Brain outputs. Cite matched rules/phrases and canonical policy IDs."
)

# --------------------------------------------------------------------------------------
# HTTP configuration
# --------------------------------------------------------------------------------------

DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner").strip()
DEEPSEEK_TIMEOUT_S = int(os.getenv("DEEPSEEK_TIMEOUT_S", "120").strip() or "120")
VAMP_BUNDLE_LIMIT = int(os.getenv("VAMP_BUNDLE_LIMIT", "60").strip() or "60")

# Optional Ollama-compatible overrides
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_API_KEY_HEADER = os.getenv("OLLAMA_API_KEY_HEADER", "Authorization").strip() or "Authorization"

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def _http_post(url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal JSON POST."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=DEEPSEEK_TIMEOUT_S) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            # Non-JSON response — return structured error with raw body
            return {"_error": "non_json_response", "raw": raw}


def _headers() -> Dict[str, str]:
    hdrs = {"Content-Type": "application/json"}
    # API key is optional for some local gateways (e.g., no-auth reverse proxy)
    if DEEPSEEK_API_KEY:
        hdrs["Authorization"] = f"Bearer {DEEPSEEK_API_KEY}"
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

def analyze_evidence_with_deepseek(item: Dict[str, Any], extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
    if not DEEPSEEK_API_URL:
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
        "model": DEEPSEEK_MODEL,
        "messages": _build_messages(SYSTEM_PROMPT, user_payload),
        "temperature": 0.2,
        # Many APIs ignore this, but include if supported
        "response_format": {"type": "json_object"}
    }

    try:
        resp = _http_post(DEEPSEEK_API_URL, _headers(), payload)
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


def analyze_feedback_with_deepseek(
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
    if not DEEPSEEK_API_URL:
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
        "model": DEEPSEEK_MODEL,
        "messages": _build_messages(SYSTEM_PROMPT, user_payload, mode_preset=mode_preset),
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        resp = _http_post(DEEPSEEK_API_URL, _headers(), payload)
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


import os
import requests


def _requests_headers(is_ollama: bool = False) -> Dict[str, str]:
    """Mirror _headers() but for requests-based helpers."""
    headers = {"Content-Type": "application/json"}

    api_key = os.environ.get("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY).strip()
    if is_ollama:
        api_key = os.environ.get("OLLAMA_API_KEY", OLLAMA_API_KEY).strip() or api_key

    if api_key:
        header_name = OLLAMA_API_KEY_HEADER if is_ollama else "Authorization"
        if header_name.lower() == "authorization" and not api_key.lower().startswith("bearer "):
            headers[header_name] = f"Bearer {api_key}"
        else:
            headers[header_name] = api_key

    return headers


def ask_deepseek(prompt: str) -> str:
    """
    Lightweight helper for single-turn prompts against a DeepSeek-compatible endpoint.

    Unlike the higher-level helpers above this function is frequently used in scripts
    and tooling, so we keep a very small surface area while still mirroring the
    defensive behaviour (timeouts, auth headers, JSON validation) used elsewhere in
    the module.
    """

    env_url = os.environ.get("DEEPSEEK_API_URL") or os.environ.get("OLLAMA_API_URL")
    url = (env_url or DEEPSEEK_API_URL).strip()
    model = (os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OLLAMA_MODEL") or DEEPSEEK_MODEL or "deepseek-reasoner").strip()

    if not url:
        return "(AI endpoint not configured)"

    is_ollama_chat = "/api/chat" in url
    is_ollama_generate = "/api/generate" in url
    is_ollama = is_ollama_chat or is_ollama_generate or "ollama" in url.lower()

    if is_ollama_generate:
        payload = {
            "model": model or "gpt-oss:120b",
            "prompt": prompt,
            "stream": False,
        }
    elif is_ollama_chat:
        payload = {
            "model": model or "gpt-oss:120b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    else:
        payload = {
            "model": model or "deepseek-reasoner",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=_requests_headers(is_ollama=is_ollama),
            timeout=DEEPSEEK_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        return f"(AI error) {exc}"

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
        return f"(AI HTTP {response.status_code}) {detail}"

    try:
        data = response.json()
    except ValueError:
        return f"(AI error) Invalid JSON response (status {response.status_code})"

    if is_ollama_generate:
        text = data.get("response") if isinstance(data, dict) else None
        return text or "(AI error) Unexpected Ollama generate response"

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
        return "(AI error) Unexpected Ollama chat response"

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return "(AI error) Unexpected response format"


def analyze_feedback_with_deepseek(prompt):
    return ask_deepseek(prompt)
