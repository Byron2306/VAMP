"""Evidence Aggregator - Orchestrates evidence routing and aggregation.

Phase 3: Evidence Aggregator
Routes evidence to appropriate handlers based on type, evidence level, and confidence.
Implements deterministic evidence aggregation with audit trails.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging
import json
from abc import ABC, abstractmethod


class EvidenceType(Enum):
    """Classification of evidence types."""
    DOCUMENT = "document"
    METADATA = "metadata"
    ATTRIBUTE = "attribute"
    RELATIONSHIP = "relationship"
    POLICY = "policy"
    AUDIT_LOG = "audit_log"
    CONFIGURATION = "configuration"
    COMPLIANCE = "compliance"


class EvidenceLevel(Enum):
    """Evidence hierarchy levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFORMATIONAL = 5


class ConfidenceScore(Enum):
    """Confidence levels for evidence validity."""
    VERIFIED = 95  # Direct system/platform validation
    HIGH = 85      # Multiple corroborating sources
    MEDIUM = 70    # Single reliable source or minor validation gaps
    LOW = 50       # Limited validation, single weak source
    UNVERIFIED = 0 # No validation performed


@dataclass
class EvidenceItem:
    """Individual evidence data point."""
    id: str
    type: EvidenceType
    level: EvidenceLevel
    confidence: int
    content: Dict[str, Any]
    source: str
    timestamp: datetime
    kpa_classification: Optional[str] = None
    audit_trail: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.audit_trail is None:
            self.audit_trail = []
        # Log initial creation
        self.log_audit("CREATED", {"type": self.type.value, "level": self.level.name})
    
    def log_audit(self, action: str, details: Dict[str, Any]):
        """Log evidence handling action for audit trail."""
        self.audit_trail.append({
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "details": details
        })


class EvidenceHandler(ABC):
    """Base class for evidence handlers."""
    
    @abstractmethod
    def can_handle(self, evidence: EvidenceItem) -> bool:
        """Check if this handler can process the evidence."""
        pass
    
    @abstractmethod
    def process(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Process evidence and return normalized results."""
        pass


class DocumentEvidenceHandler(EvidenceHandler):
    """Handles document evidence items."""
    
    def can_handle(self, evidence: EvidenceItem) -> bool:
        return evidence.type == EvidenceType.DOCUMENT
    
    def process(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Extract and normalize document evidence."""
        evidence.log_audit("PROCESS_DOCUMENT", {"content_keys": list(evidence.content.keys())})
        
        return {
            "document_id": evidence.id,
            "classification": evidence.kpa_classification,
            "confidence": evidence.confidence,
            "properties": evidence.content,
            "normalized_at": datetime.now().isoformat()
        }


class MetadataEvidenceHandler(EvidenceHandler):
    """Handles metadata evidence items."""
    
    def can_handle(self, evidence: EvidenceItem) -> bool:
        return evidence.type == EvidenceType.METADATA
    
    def process(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Extract and normalize metadata."""
        evidence.log_audit("PROCESS_METADATA", {"fields": len(evidence.content)})
        
        return {
            "metadata_id": evidence.id,
            "fields": evidence.content,
            "confidence": evidence.confidence,
            "source": evidence.source,
            "normalized_at": datetime.now().isoformat()
        }


class AuditLogEvidenceHandler(EvidenceHandler):
    """Handles audit log evidence."""
    
    def can_handle(self, evidence: EvidenceItem) -> bool:
        return evidence.type == EvidenceType.AUDIT_LOG
    
    def process(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Process audit log entries."""
        evidence.log_audit("PROCESS_AUDIT_LOG", {"entries": len(evidence.content.get('entries', []))})
        
        return {
            "audit_id": evidence.id,
            "entries": evidence.content.get('entries', []),
            "compliance_relevance": evidence.kpa_classification,
            "confidence": evidence.confidence,
            "normalized_at": datetime.now().isoformat()
        }


class EvidenceAggregator:
    """Orchestrates evidence aggregation and routing.
    
    Phase 3: Evidence Aggregator
    Routes evidence to appropriate handlers for normalization and scoring.
    Maintains deterministic, auditable processing.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("EvidenceAggregator")
        self.handlers: List[EvidenceHandler] = [
            DocumentEvidenceHandler(),
            MetadataEvidenceHandler(),
            AuditLogEvidenceHandler()
        ]
        self.aggregated_evidence: Dict[str, List[Dict]] = {}
        self.processing_audit: List[Dict[str, Any]] = []
    
    def aggregate(self, evidence_items: List[EvidenceItem]) -> Dict[str, Any]:
        """Aggregate and process multiple evidence items.
        
        Args:
            evidence_items: List of evidence items to process
            
        Returns:
            Dictionary with aggregated results and audit trail
        """
        results = {
            "timestamp": datetime.now().isoformat(),
            "total_items": len(evidence_items),
            "by_type": {},
            "by_level": {},
            "normalized_evidence": []
        }
        
        for evidence in evidence_items:
            # Find appropriate handler
            handler = self._find_handler(evidence)
            if handler:
                try:
                    processed = handler.process(evidence)
                    results["normalized_evidence"].append(processed)
                    
                    # Track by type
                    etype = evidence.type.value
                    if etype not in results["by_type"]:
                        results["by_type"][etype] = 0
                    results["by_type"][etype] += 1
                    
                    # Track by level
                    elevel = evidence.level.name
                    if elevel not in results["by_level"]:
                        results["by_level"][elevel] = 0
                    results["by_level"][elevel] += 1
                    
                    # Log processing
                    self.processing_audit.append({
                        "evidence_id": evidence.id,
                        "handler": handler.__class__.__name__,
                        "status": "SUCCESS",
                        "timestamp": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    self.logger.error(f"Error processing evidence {evidence.id}: {str(e)}")
                    self.processing_audit.append({
                        "evidence_id": evidence.id,
                        "handler": handler.__class__.__name__,
                        "status": "ERROR",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
            else:
                self.logger.warning(f"No handler found for evidence type: {evidence.type}")
        
        results["audit_trail"] = self.processing_audit
        return results
    
    def _find_handler(self, evidence: EvidenceItem) -> Optional[EvidenceHandler]:
        """Find appropriate handler for evidence item."""
        for handler in self.handlers:
            if handler.can_handle(evidence):
                return handler
        return None
    
    def route_by_confidence(self, evidence_items: List[EvidenceItem]) -> Dict[str, List[EvidenceItem]]:
        """Route evidence by confidence thresholds.
        
        Args:
            evidence_items: Evidence to route
            
        Returns:
            Routed evidence by confidence category
        """
        routed = {
            "verified": [],
            "high": [],
            "medium": [],
            "low": [],
            "unverified": []
        }
        
        for evidence in evidence_items:
            if evidence.confidence >= ConfidenceScore.VERIFIED.value:
                routed["verified"].append(evidence)
            elif evidence.confidence >= ConfidenceScore.HIGH.value:
                routed["high"].append(evidence)
            elif evidence.confidence >= ConfidenceScore.MEDIUM.value:
                routed["medium"].append(evidence)
            elif evidence.confidence >= ConfidenceScore.LOW.value:
                routed["low"].append(evidence)
            else:
                routed["unverified"].append(evidence)
        
        return routed
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Get complete audit trail of all processing."""
        return self.processing_audit.copy()


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Create sample evidence
    evidence1 = EvidenceItem(
        id="doc_001",
        type=EvidenceType.DOCUMENT,
        level=EvidenceLevel.HIGH,
        confidence=ConfidenceScore.HIGH.value,
        content={"title": "Policy Document", "content": "Sample content"},
        source="sharepoint",
        timestamp=datetime.now(),
        kpa_classification="Policy"
    )
    
    evidence2 = EvidenceItem(
        id="meta_001",
        type=EvidenceType.METADATA,
        level=EvidenceLevel.MEDIUM,
        confidence=ConfidenceScore.VERIFIED.value,
        content={"created_by": "admin", "modified_date": "2025-01-15"},
        source="system",
        timestamp=datetime.now(),
        kpa_classification="Metadata"
    )
    
    # Aggregate evidence
    aggregator = EvidenceAggregator()
    results = aggregator.aggregate([evidence1, evidence2])
    
    # Display results
    print(json.dumps(results, indent=2, default=str))
