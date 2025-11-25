# PDF Implementation Roadmap for VAMP

## Executive Summary

This document tracks the implementation of all decisions from the Grant-1 vs Byron-2306 VAMP analysis PDF (November 25, 2025). The goal is to transform VAMP from a raw scanner into a complete intelligence pipeline with deterministic scoring, evidence routing, director approval workflows, and self-learning capabilities.

**Key Decision**: Remove Ollama entirely. VAMP needs orchestration and routing, not LLM reasoning.

---

## Phase 1: Remove Ollama Completely

**Status**: IN_PROGRESS

### 1.1 Delete Ollama Files
- [ ] Delete `backend/ollama_client.py` (923 lines)
- [ ] Delete `tests/test_ollama_client.py`
- [ ] Remove `OLLAMA_*` environment variables from `.env.example`

### 1.2 Remove Ollama Imports
- [ ] Remove line 15 from `backend/agent_app/api.py`: `from ..ollama_client import describe_ai_backend`
- [ ] Remove `describe_ai_backend` call from health check endpoint (line 54)
- [ ] Remove any `ask_ollama()` calls from codebase

### 1.3 Update Documentation
- [ ] Remove Ollama setup section from `README.md`
- [ ] Remove Ollama tests from `setup_backend.bat`
- [ ] Add note explaining "Why we removed Ollama"

### 1.4 Create Decision Document
- [ ] Create `docs/OLLAMA_REMOVAL_DECISION.md`

---

## Phase 2: Build Evidence Transformer

**Status**: PENDING

**File**: `backend/evidence_transformer.py`

### Purpose
Transform raw VAMP scan output (hash, platform, title, body) into scored, tiered, policy-checked evidence ready for director review.

### Features
1. KPA Classification via keyword matching
2. Evidence Tiering (Compliance / Developmental / Transformational)
3. Policy Validation against configured policy matrix
4. Confidence calculation
5. Cross-platform deduplication

### Key Classes
```python
class EvidenceTransformer:
    def __init__(self, kpa_config, tier_keywords, policy_registry)
    def transform(self, vamp_item: Dict) -> Dict
    def classify_kpa(self, text: str) -> List[Tuple[str, float]]
    def classify_tier(self, item: Dict, kpas: List[str]) -> List[str]
    def check_policies(self, item: Dict) -> List[str]
```

---

## Phase 3: Build Evidence Aggregator

**Status**: PENDING

**File**: `backend/evidence_aggregator.py`

### Purpose
Collect evidence from all platforms (Outlook, OneDrive, eFundi, etc.), deduplicate, and compute cross-KPA bonuses.

### Features
1. Batch collection from multiple platforms
2. SHA256-based deduplication
3. Cross-KPA membership detection (+0.5 bonus per additional KPA)
4. Evidence ranking by confidence
5. Staging for director review

### Key Classes
```python
class EvidenceAggregator:
    def __init__(self)
    def add_batch(self, platform: str, items: List[Dict])
    def finalize(self) -> List[Dict]
    def compute_cross_kpa_bonus(self) -> Dict[str, float]
    def get_deduped_count(self) -> int
```

---

## Phase 4: Build HR Approval Layer

**Status**: PENDING

**Files**:
- `backend/agent_app/rbac.py` - Role-based access control
- `backend/hr_approval_layer.py` - Approval workflows

### Purpose
Implement director/HR review queue, approval logic, and role-based access control.

### Roles
- `employee` - Can submit evidence only
- `director` - Can review, approve, request edits
- `hr_audit` - Can audit all decisions, export reports
- `admin` - System configuration

### Features
1. Evidence review queue with routing
2. Director approval/rejection/edit requests
3. HR audit trail
4. Access control enforcement
5. Approval metrics tracking

### Key Classes
```python
class AuthContext:
    def __init__(self, userid: str, role: str, permissions: Set[str])
    def can_submit(self) -> bool
    def can_review(self) -> bool
    def can_audit(self) -> bool

class ApprovalWorkflow:
    def submit_for_review(self, evidence_batch, submitter_id) -> review_id
    def approve(self, review_id, director_id, notes) -> bool
    def request_edits(self, review_id, reasons) -> bool
    def get_review_status(self, review_id) -> Dict
```

---

## Phase 5: Add WebDAV Connector

**Status**: PENDING

**File**: `backend/webdav_connector.py`

### Purpose
Direct file access to eFundi/Nextcloud via WebDAV instead of DOM parsing.

### Features
1. WebDAV authentication
2. Recursive file listing
3. File content extraction (MIME-aware)
4. Timestamp extraction
5. Integration with existing scrapers

### Key Classes
```python
class WebDAVConnector:
    def __init__(self, url: str, username: str, password: str)
    def scan_recursive(self, remote_path: str) -> List[Dict]
    def download_file(self, remote_path: str) -> bytes
    def extract_text(self, file_bytes: bytes, mime_type: str) -> str
```

---

## Phase 6: Build Reflection Engine

**Status**: PENDING

**Files**:
- `backend/reflection_parser.py` - Parse reflection data
- `frontend/reflection_form.html` - Capture form (browser extension)

### Purpose
Capture and analyze employee self-assessment reflections for growth feedback.

### Features
1. Reflection capture form (What went well, What didn't, Lessons, Values alignment)
2. Text parsing for alignment indicators
3. Storage with encryption
4. Director review of reflections
5. Growth feedback generation

### Key Classes
```python
class ReflectionForm:
    def __init__(self)
    def capture(self) -> Dict[str, str]
    def validate(self) -> bool

class ReflectionParser:
    def __init__(self, nwu_values_list)
    def parse(self, reflection_text: str) -> Dict
    def extract_values_alignment(self, text: str) -> List[Tuple[str, float]]
    def detect_growth_indicators(self, text: str) -> List[str]
```

---

## Phase 7: Build Orchestrator

**Status**: PENDING

**File**: `backend/evidence_orchestrator.py`

### Purpose
Unify the entire pipeline: scan -> transform -> aggregate -> route -> approve.

### Features
1. Coordinates all subsystems
2. Manages evidence lifecycle
3. Handles error recovery
4. Provides progress callbacks
5. Updates setup_backend.bat with new startup sequence

### Key Classes
```python
class EvidenceOrchestrator:
    def __init__(self)
    def scan_all_platforms(self) -> List[Dict]
    def transform_evidence(self, items: List[Dict]) -> List[Dict]
    def aggregate_evidence(self, items: List[Dict]) -> List[Dict]
    def route_evidence(self, items: List[Dict]) -> Dict[str, List[Dict]]
    def get_pipeline_status(self) -> Dict
```

---

## Implementation Timeline

| Phase | Task | Effort | Status |
|-------|------|--------|--------|
| 1 | Remove Ollama | 4 hours | IN_PROGRESS |
| 2 | Evidence Transformer | 12 hours | PENDING |
| 3 | Evidence Aggregator | 10 hours | PENDING |
| 4 | HR Approval Layer + RBAC | 16 hours | PENDING |
| 5 | WebDAV Connector | 8 hours | PENDING |
| 6 | Reflection Engine | 12 hours | PENDING |
| 7 | Orchestrator + Integration | 14 hours | PENDING |
| 8 | Testing + QA | 16 hours | PENDING |
| 9 | Documentation + Deployment | 8 hours | PENDING |
| **TOTAL** | | **100 hours** | |

---

## Success Criteria

When complete, VAMP will:

1. ✅ Have ZERO LLM/Ollama dependencies
2. ✅ Transform raw scan output into scored, tiered evidence
3. ✅ Deduplicate evidence across platforms
4. ✅ Route evidence through director approval workflow
5. ✅ Capture employee reflections
6. ✅ Track learning signals from director feedback
7. ✅ Generate audit trails for compliance
8. ✅ Support multiple institutions via config
9. ✅ Run deterministic, auditable scoring
10. ✅ Enforce POPIA/policy compliance

---

## Decision Record

**Date**: November 25, 2025  
**Decision**: Implement all phases in the order listed  
**Rationale**: Create a complete, deterministic intelligence pipeline aligned with the PDF spec  
**Owner**: Byron2306  
**Status**: APPROVED
