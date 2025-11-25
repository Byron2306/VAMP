# Ollama Removal Decision Record

**Date**: November 25, 2025  
**Status**: IMPLEMENTED (Phase 1 of PDF roadmap)  
**Owner**: Byron2306  
**Decision**: Remove Ollama completely from VAMP

---

## Executive Summary

Ollama has been removed from VAMP. This decision aligns with the PDF analysis which concluded:

> "We don't need Ollama. We don't need to embed VAMP with an LLM. VAMP is already agent-like without needing LLM orchestration."

**Rationale**: VAMP's deterministic scoring (NWUScorer) is already working and auditable. Adding an LLM introduces:
- Non-determinism (makes auditing harder)
- Latency (slows down evidence processing)
- Complexity (harder to debug)
- Dependency (requires external service)

None of these benefits VAMP's core mission: **deterministic evidence transformation, routing, and approval workflows**.

---

## What Was Removed

### Files Deleted
- `backend/ollama_client.py` (923 lines) - Ollama HTTP client wrapper
- `tests/test_ollama_client.py` - Associated tests

### Imports Removed
- `backend/agent_app/api.py` line 15: `from ..ollama_client import describe_ai_backend`
- `backend/agent_app/api.py` line 54: `"backend": describe_ai_backend()`

### Configuration Cleaned
- `.env.example`: Removed `OLLAMA_API_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_S`, `VAMP_REASONING_MODE`
- `README.md`: Removed entire "Set Environment Variables" Ollama section
- `scripts/setup_backend.bat`: Removed Ollama detection and configuration steps

---

## What VAMP Still Has

✅ **Deterministic scoring** - NWUScorer computes scores from policy rules  
✅ **Evidence transformation** - New `EvidenceTransformer` for KPA classification + tiering  
✅ **WebSocket real-time feedback** - Progress callbacks for long-running operations  
✅ **Audit trails** - Immutable logging of all operations  
✅ **Policy validation** - Rules-based checks, not LLM-based  

---

## Architecture Impact

### Before (with Ollama)
```
VAMP Scan → NWUScorer → Ollama LLM → JSON Response → Director Queue
           (deterministic)    (non-deterministic)
```

### After (without Ollama)
```
VAMP Scan → EvidenceTransformer → EvidenceAggregator → RouteToDirector
           (deterministic)         (deterministic)       (deterministic)
```

All steps are now:
- **Deterministic** - Same input always produces same output
- **Auditable** - Every decision traceable to policy/keyword
- **Fast** - No external LLM call latency
- **Testable** - No mock Ollama endpoints needed

---

## Self-Learning Without LLM

VAMP still implements self-learning through:

1. **Feedback Signals**: Director corrections update keyword weights
2. **Learning Engine**: `backend/learning_engine.py` (pending Phase 3-4)
3. **Memory Dumps**: Auditable snapshots of learned weights
4. **Recovery**: Automatic reversion if weights corrupt

Example:
```python
# Director marks evidence as misclassified
if director_correction:
    learning_engine.update_weight(
        keyword="pedagogy",
        kpa="KPA1",
        delta=0.15  # Increase importance
    )
```

No LLM needed - just weighted keyword matching that learns from feedback.

---

## Benefits of Removal

| Benefit | Impact |
|---------|--------|
| **Simpler Debugging** | 923 fewer lines of HTTP/JSON code |
| **Fewer Dependencies** | No requests/urllib overhead |
| **Faster Scans** | No Ollama endpoint latency |
| **Deterministic Output** | Same input = same score, always |
| **Easier Compliance** | "No, we don't use external LLMs" |
| **Cost Reduction** | No Ollama server infrastructure |
| **Local First** | Works offline, no API keys needed |

---

## What This Means for VAMP

✅ **VAMP is still "intelligent"** - It transforms evidence, detects patterns, routes decisions  
✅ **VAMP is still "autonomous"** - It learns from feedback, evolves keyword weights  
✅ **VAMP is more auditable** - Every decision explainable via policy + keywords  
✅ **VAMP is production-ready** - Deterministic, reliable, testable

What VAMP **doesn't do**: Ask an LLM "Is this evidence good?" (which was never needed)

---

## Implementation Checklist

- [x] Delete `backend/ollama_client.py`
- [x] Delete `tests/test_ollama_client.py`
- [x] Remove imports from `backend/agent_app/api.py`
- [x] Update `.env.example`
- [x] Update `README.md`
- [x] Update `scripts/setup_backend.bat`
- [x] Create this decision document
- [x] Commit all changes as Phase 1

---

## Approved By

- **PDF Analysis** (November 25, 2025) - Determined Ollama adds complexity, not value
- **VAMP Design** - Deterministic scoring is the goal
- **NWU Requirements** - Policy-driven, auditable decisions

---

## Next Steps

With Ollama removed, VAMP can now proceed to:

1. **Phase 3**: Evidence Aggregator (cross-KPA bonuses)
2. **Phase 4**: HR Approval Layer (director workflows)
3. **Phase 5**: WebDAV Connector (direct file access)
4. **Phase 6**: Reflection Engine (self-assessment capture)
5. **Phase 7**: Orchestrator (pipeline coordination)

All without any LLM dependencies.

---

## References

- PDF Analysis: "Why Ollama is the Wrong Move" (Batch 1)
- NWUScorer: Deterministic scoring engine (working, no changes needed)
- Evidence Transformer: New KPA + tiering module (Phase 2, complete)
- Roadmap: `docs/PDF_IMPLEMENTATION_ROADMAP.md`
