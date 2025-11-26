"""
Phase 7: Evidence Orchestrator
Central orchestration layer coordinating all evidence processing components
Implements deterministic workflow state management, audit trails, and REST API endpoints
No LLM dependencies - all processing is deterministic and auditable
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
import hashlib


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrchestrationStatus(Enum):
    """Workflow state for evidence processing"""
    PENDING = "pending"
    TRANSFORMED = "transformed"
    AGGREGATED = "aggregated"
    APPROVED = "approved"
    PARSED = "parsed"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ProcessingStage(Enum):
    """Evidence processing pipeline stages"""
    INPUT = "input"
    TRANSFORMATION = "transformation"
    AGGREGATION = "aggregation"
    APPROVAL = "approval"
    REFLECTION = "reflection"
    WEBDAV_STORAGE = "webdav_storage"
    COMPLETION = "completion"


@dataclass
class AuditEntry:
    """Immutable audit trail entry for all orchestration operations"""
    timestamp: str
    stage: ProcessingStage
    status: OrchestrationStatus
    operation: str
    evidence_id: str
    user_id: Optional[str]
    role: Optional[str]
    changes: Dict[str, Any]
    error_message: Optional[str] = None
    entry_hash: str = field(default="")
    previous_hash: str = field(default="")
    
    def __post_init__(self):
        """Calculate hash for audit entry integrity"""
        entry_data = f"{self.timestamp}{self.stage.value}{self.status.value}{self.evidence_id}{json.dumps(self.changes, sort_keys=True)}"
        self.entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()


@dataclass
class OrchestrationState:
    """Complete state snapshot for evidence processing workflow"""
    evidence_id: str
    current_status: OrchestrationStatus
    current_stage: ProcessingStage
    created_at: str
    updated_at: str
    transformed_evidence: Optional[Dict[str, Any]] = None
    aggregated_result: Optional[Dict[str, Any]] = None
    approval_decision: Optional[Dict[str, Any]] = None
    reflection_insights: Optional[Dict[str, Any]] = None
    webdav_location: Optional[str] = None
    audit_trail: List[AuditEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    
    def add_audit_entry(self, entry: AuditEntry):
        """Add entry to immutable audit trail"""
        if self.audit_trail:
            entry.previous_hash = self.audit_trail[-1].entry_hash
        self.audit_trail.append(entry)
        logger.info(f"Audit entry added for {self.evidence_id}: {entry.operation}")
    
    def get_state_hash(self) -> str:
        """Generate hash of current state for integrity verification"""
        state_data = f"{self.evidence_id}{self.current_status.value}{self.current_stage.value}{self.updated_at}"
        return hashlib.sha256(state_data.encode()).hexdigest()


class WorkflowComponent(ABC):
    """Abstract base for pluggable workflow components"""
    
    @abstractmethod
    async def process(self, evidence: Dict[str, Any], state: OrchestrationState) -> Dict[str, Any]:
        """Process evidence and return results"""
        pass
    
    @abstractmethod
    def get_component_name(self) -> str:
        """Return component name for logging"""
        pass


class MockEvidenceTransformer(WorkflowComponent):
    """Mock Evidence Transformer (Phase 2) for orchestration"""
    
    async def process(self, evidence: Dict[str, Any], state: OrchestrationState) -> Dict[str, Any]:
        """Transform evidence into standardized format"""
        logger.info(f"Transforming evidence: {state.evidence_id}")
        
        # Mock transformation with confidence scoring
        transformed = {
            "original_id": evidence.get("id"),
            "type": evidence.get("type", "document"),
            "content": evidence.get("content", ""),
            "confidence": 0.95,
            "transformation_timestamp": datetime.utcnow().isoformat(),
            "metadata": evidence.get("metadata", {})
        }
        
        return transformed
    
    def get_component_name(self) -> str:
        return "EvidenceTransformer"


class MockEvidenceAggregator(WorkflowComponent):
    """Mock Evidence Aggregator (Phase 3) for orchestration"""
    
    async def process(self, evidence: Dict[str, Any], state: OrchestrationState) -> Dict[str, Any]:
        """Aggregate evidence with routing logic"""
        logger.info(f"Aggregating evidence: {state.evidence_id}")
        
        # Mock aggregation with classification
        aggregated = {
            "evidence_id": state.evidence_id,
            "classification": "high_priority",
            "aggregation_score": 0.87,
            "route": "approval_required",
            "summary": f"Aggregated evidence for {evidence.get('type', 'unknown')} type",
            "aggregation_timestamp": datetime.utcnow().isoformat()
        }
        
        return aggregated
    
    def get_component_name(self) -> str:
        return "EvidenceAggregator"


class MockHRApprovalLayer(WorkflowComponent):
    """Mock HR Approval Layer (Phase 4) for orchestration"""
    
    async def process(self, evidence: Dict[str, Any], state: OrchestrationState) -> Dict[str, Any]:
        """Apply RBAC and approval logic"""
        logger.info(f"Applying HR approval: {state.evidence_id}")
        
        # Mock approval with RBAC
        approval = {
            "evidence_id": state.evidence_id,
            "approved": True,
            "approval_role": "hr_manager",
            "approval_level": "standard",
            "notes": "Evidence meets compliance requirements",
            "approval_timestamp": datetime.utcnow().isoformat()
        }
        
        return approval
    
    def get_component_name(self) -> str:
        return "HRApprovalLayer"


class MockReflectionParser(WorkflowComponent):
    """Mock Reflection Parser (Phase 6) for orchestration"""
    
    async def process(self, evidence: Dict[str, Any], state: OrchestrationState) -> Dict[str, Any]:
        """Parse decisions and generate feedback forms"""
        logger.info(f"Parsing reflection: {state.evidence_id}")
        
        # Mock reflection parsing
        insights = {
            "evidence_id": state.evidence_id,
            "decision_category": "compliance_review",
            "confidence_level": 0.92,
            "feedback_required": False,
            "insights": [
                "Evidence demonstrates proper documentation",
                "All required fields populated correctly"
            ],
            "parsing_timestamp": datetime.utcnow().isoformat()
        }
        
        return insights
    
    def get_component_name(self) -> str:
        return "ReflectionParser"


class WebDAVConnector:
    """WebDAV storage coordinator (Phase 5 integration)"""
    
    async def store(self, evidence_id: str, content: Dict[str, Any]) -> str:
        """Store evidence in WebDAV and return location"""
        logger.info(f"Storing evidence in WebDAV: {evidence_id}")
        
        # Mock WebDAV storage location
        location = f"/vamp/evidence/{evidence_id}/processed_{datetime.utcnow().timestamp()}"
        
        return location
    
    async def retrieve(self, location: str) -> Dict[str, Any]:
        """Retrieve evidence from WebDAV storage"""
        logger.info(f"Retrieving evidence from WebDAV: {location}")
        
        # Mock retrieval
        return {"location": location, "retrieved_at": datetime.utcnow().isoformat()}


class EvidenceOrchestrator:
    """
    Central orchestration layer coordinating all evidence processing phases.
    Manages workflow state, audit trails, and deterministic error recovery.
    """
    
    def __init__(self):
        self.components: Dict[str, WorkflowComponent] = {
            "transformer": MockEvidenceTransformer(),
            "aggregator": MockEvidenceAggregator(),
            "approver": MockHRApprovalLayer(),
            "parser": MockReflectionParser()
        }
        self.webdav = WebDAVConnector()
        self.states: Dict[str, OrchestrationState] = {}
        self.batch_size = 10
    
    def create_workflow_state(self, evidence_id: str, evidence: Dict[str, Any]) -> OrchestrationState:
        """Initialize new orchestration state"""
        now = datetime.utcnow().isoformat()
        
        state = OrchestrationState(
            evidence_id=evidence_id,
            current_status=OrchestrationStatus.PENDING,
            current_stage=ProcessingStage.INPUT,
            created_at=now,
            updated_at=now,
            metadata={"source": evidence.get("source", "unknown")}
        )
        
        # Add initial audit entry
        initial_entry = AuditEntry(
            timestamp=now,
            stage=ProcessingStage.INPUT,
            status=OrchestrationStatus.PENDING,
            operation="workflow_initialized",
            evidence_id=evidence_id,
            user_id=evidence.get("user_id"),
            role=evidence.get("role"),
            changes={"initial": True}
        )
        state.add_audit_entry(initial_entry)
        
        self.states[evidence_id] = state
        return state
    
    async def orchestrate_evidence(self, evidence: Dict[str, Any]) -> OrchestrationState:
        """
        Execute complete evidence orchestration pipeline
        Stages: Transform → Aggregate → Approve → Reflect → Store
        """
        evidence_id = evidence.get("id", str(uuid.uuid4()))
        state = self.create_workflow_state(evidence_id, evidence)
        
        try:
            # Stage 1: Transformation
            logger.info(f"Starting orchestration for evidence: {evidence_id}")
            state.current_stage = ProcessingStage.TRANSFORMATION
            state.current_status = OrchestrationStatus.PENDING
            
            transformed = await self.components["transformer"].process(evidence, state)
            state.transformed_evidence = transformed
            state.current_status = OrchestrationStatus.TRANSFORMED
            
            self._add_workflow_audit(state, ProcessingStage.TRANSFORMATION, "transformation_complete", evidence)
            
            # Stage 2: Aggregation
            state.current_stage = ProcessingStage.AGGREGATION
            aggregated = await self.components["aggregator"].process(transformed, state)
            state.aggregated_result = aggregated
            
            self._add_workflow_audit(state, ProcessingStage.AGGREGATION, "aggregation_complete", evidence)
            
            # Stage 3: Approval
            state.current_stage = ProcessingStage.APPROVAL
            approval = await self.components["approver"].process(aggregated, state)
            state.approval_decision = approval
            state.current_status = OrchestrationStatus.APPROVED
            
            self._add_workflow_audit(state, ProcessingStage.APPROVAL, "approval_complete", evidence)
            
            # Stage 4: Reflection Parsing
            state.current_stage = ProcessingStage.REFLECTION
            insights = await self.components["parser"].process(approval, state)
            state.reflection_insights = insights
            state.current_status = OrchestrationStatus.PARSED
            
            self._add_workflow_audit(state, ProcessingStage.REFLECTION, "reflection_complete", evidence)
            
            # Stage 5: WebDAV Storage
            state.current_stage = ProcessingStage.WEBDAV_STORAGE
            location = await self.webdav.store(evidence_id, {
                "transformed": state.transformed_evidence,
                "aggregated": state.aggregated_result,
                "approved": state.approval_decision,
                "insights": state.reflection_insights
            })
            state.webdav_location = location
            
            self._add_workflow_audit(state, ProcessingStage.WEBDAV_STORAGE, "storage_complete", {"location": location})
            
            # Stage 6: Completion
            state.current_stage = ProcessingStage.COMPLETION
            state.current_status = OrchestrationStatus.COMPLETED
            state.updated_at = datetime.utcnow().isoformat()
            
            self._add_workflow_audit(state, ProcessingStage.COMPLETION, "orchestration_complete", {})
            
            logger.info(f"Orchestration completed successfully for {evidence_id}")
            
        except Exception as e:
            logger.error(f"Orchestration failed for {evidence_id}: {str(e)}")
            state.current_status = OrchestrationStatus.FAILED
            state.updated_at = datetime.utcnow().isoformat()
            
            self._add_workflow_audit(
                state,
                state.current_stage,
                "orchestration_failed",
                {"error": str(e)}
            )
            
            # Attempt recovery if retries available
            if state.retry_count < state.max_retries:
                logger.info(f"Attempting retry {state.retry_count + 1} for {evidence_id}")
                state.retry_count += 1
                return await self.orchestrate_evidence(evidence)
        
        return state
    
    def _add_workflow_audit(self, state: OrchestrationState, stage: ProcessingStage, operation: str, changes: Dict[str, Any]):
        """Add audit entry for workflow stage"""
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat(),
            stage=stage,
            status=state.current_status,
            operation=operation,
            evidence_id=state.evidence_id,
            user_id=state.metadata.get("user_id"),
            role=state.metadata.get("role"),
            changes=changes
        )
        state.add_audit_entry(entry)
    
    async def orchestrate_batch(self, evidence_list: List[Dict[str, Any]]) -> List[OrchestrationState]:
        """Process multiple evidence items with batch coordination"""
        logger.info(f"Starting batch orchestration: {len(evidence_list)} items")
        
        results = []
        for i in range(0, len(evidence_list), self.batch_size):
            batch = evidence_list[i:i + self.batch_size]
            
            for evidence in batch:
                result = await self.orchestrate_evidence(evidence)
                results.append(result)
        
        logger.info(f"Batch orchestration completed: {len(results)} items processed")
        return results
    
    def get_orchestration_status(self, evidence_id: str) -> Optional[OrchestrationState]:
        """Retrieve current orchestration state"""
        return self.states.get(evidence_id)
    
    def get_audit_trail
