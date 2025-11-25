"""HR Approval Layer - Manages evidence approval workflows for HR decision-making.

Phase 4.2: HR Approval Layer
Orchestrates multi-level approval workflows with RBAC integration.
Maintains deterministic approval chains with full audit trails.
"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging
import uuid


class ApprovalStatus(Enum):
    """Workflow approval statuses."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    ARCHIVED = "archived"


class EvidenceDecision(Enum):
    """HR decisions on evidence."""
    APPROVED_FOR_HR_USE = "approved_for_hr_use"
    REQUIRES_CLARIFICATION = "requires_clarification"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    POLICY_VIOLATION = "policy_violation"
    APPROVED_WITH_CAVEATS = "approved_with_caveats"


@dataclass
class ApprovalRequest:
    """Evidence approval request in workflow."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_id: str = ""
    evidence_type: str = ""
    requester_id: str = ""
    assigned_to: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None
    approvals: List[Dict] = field(default_factory=list)
    rejections: List[Dict] = field(default_factory=list)
    notes: str = ""
    priority: int = 3  # 1=critical, 5=low
    
    def add_approval(self, approver_id: str, decision: str, comments: str = ""):
        """Record an approval decision."""
        self.approvals.append({
            "approver_id": approver_id,
            "decision": decision,
            "comments": comments,
            "timestamp": datetime.now().isoformat()
        })
    
    def add_rejection(self, rejector_id: str, reason: str, comments: str = ""):
        """Record a rejection decision."""
        self.rejections.append({
            "rejector_id": rejector_id,
            "reason": reason,
            "comments": comments,
            "timestamp": datetime.now().isoformat()
        })


class ApprovalRule:
    """Rules for automated approval decisions."""
    
    def __init__(self, name: str, rule_type: str):
        self.name = name
        self.rule_type = rule_type  # 'auto_approve', 'auto_reject', 'escalate'
        self.conditions: List[Dict] = []
        self.enabled = True
    
    def add_condition(self, field: str, operator: str, value: any):
        """Add condition to rule."""
        self.conditions.append({
            "field": field,
            "operator": operator,  # 'eq', 'lt', 'gt', 'contains', etc.
            "value": value
        })
    
    def evaluate(self, context: Dict) -> bool:
        """Check if rule conditions match context."""
        if not self.enabled:
            return False
        
        for condition in self.conditions:
            field_value = context.get(condition["field"])
            if not self._evaluate_condition(field_value, condition):
                return False
        
        return True
    
    def _evaluate_condition(self, value: any, condition: Dict) -> bool:
        """Evaluate single condition."""
        operator = condition["operator"]
        expected = condition["value"]
        
        if operator == "eq":
            return value == expected
        elif operator == "lt":
            return value < expected
        elif operator == "gt":
            return value > expected
        elif operator == "contains":
            return expected in value if value else False
        elif operator == "in":
            return value in expected
        
        return False


class ApprovalWorkflow:
    """Multi-level approval workflow orchestrator."""
    
    def __init__(self):
        self.logger = logging.getLogger("ApprovalWorkflow")
        self.requests: Dict[str, ApprovalRequest] = {}
        self.rules: List[ApprovalRule] = []
        self.approval_chain: Dict[str, List[str]] = {}  # evidence_type -> approver chain
        self.audit_trail: List[Dict] = []
    
    def create_approval_request(self, evidence_id: str, evidence_type: str, requester_id: str) -> ApprovalRequest:
        """Create new approval request for evidence."""
        request = ApprovalRequest(
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            requester_id=requester_id,
            assigned_to=self._get_next_approver(evidence_type)
        )
        
        self.requests[request.request_id] = request
        self._log_action("CREATED", request.request_id, requester_id, f"Evidence: {evidence_id}")
        
        return request
    
    def submit_approval(self, request_id: str, approver_id: str, decision: EvidenceDecision, comments: str = ""):
        """Submit approval decision."""
        request = self.requests.get(request_id)
        if not request:
            self.logger.warning(f"Request not found: {request_id}")
            return False
        
        request.add_approval(approver_id, decision.value, comments)
        
        # Check if more approvals needed
        if self._needs_more_approvals(request):
            # Route to next approver
            next_approver = self._get_next_approver(request.evidence_type)
            request.assigned_to = next_approver
            request.status = ApprovalStatus.PENDING
        else:
            # Workflow complete
            request.status = ApprovalStatus.APPROVED
        
        self._log_action("APPROVED", request_id, approver_id, f"Decision: {decision.value}")
        return True
    
    def submit_rejection(self, request_id: str, rejector_id: str, reason: str, comments: str = ""):
        """Submit rejection decision."""
        request = self.requests.get(request_id)
        if not request:
            self.logger.warning(f"Request not found: {request_id}")
            return False
        
        request.add_rejection(rejector_id, reason, comments)
        request.status = ApprovalStatus.REJECTED
        
        self._log_action("REJECTED", request_id, rejector_id, f"Reason: {reason}")
        return True
    
    def escalate_request(self, request_id: str, reason: str):
        """Escalate request to higher authority."""
        request = self.requests.get(request_id)
        if not request:
            return False
        
        # Get escalation approver (usually manager level)
        request.assigned_to = self._get_escalation_approver(request.evidence_type)
        request.status = ApprovalStatus.ESCALATED
        
        self._log_action("ESCALATED", request_id, "system", f"Reason: {reason}")
        return True
    
    def add_approval_rule(self, rule: ApprovalRule):
        """Add automated approval rule."""
        self.rules.append(rule)
    
    def evaluate_auto_approval(self, request_id: str, context: Dict) -> Optional[EvidenceDecision]:
        """Evaluate if request can be auto-approved."""
        for rule in self.rules:
            if rule.rule_type == "auto_approve" and rule.evaluate(context):
                self._log_action("AUTO_APPROVED", request_id, "system", f"Rule: {rule.name}")
                return EvidenceDecision.APPROVED_FOR_HR_USE
            elif rule.rule_type == "auto_reject" and rule.evaluate(context):
                self._log_action("AUTO_REJECTED", request_id, "system", f"Rule: {rule.name}")
                return EvidenceDecision.INSUFFICIENT_EVIDENCE
        
        return None
    
    def get_pending_requests(self, approver_id: str) -> List[ApprovalRequest]:
        """Get pending requests for approver."""
        return [
            req for req in self.requests.values()
            if req.assigned_to == approver_id and req.status == ApprovalStatus.PENDING
        ]
    
    def _needs_more_approvals(self, request: ApprovalRequest) -> bool:
        """Check if more approvals needed based on policy."""
        # Policy: critical items need 2 approvals
        if request.priority == 1:
            return len(request.approvals) < 2
        # Standard items need 1 approval
        return len(request.approvals) < 1
    
    def _get_next_approver(self, evidence_type: str) -> str:
        """Get next approver in chain."""
        chain = self.approval_chain.get(evidence_type, [])
        return chain[0] if chain else "hr_specialist"
    
    def _get_escalation_approver(self, evidence_type: str) -> str:
        """Get escalation-level approver."""
        return "hr_manager"
    
    def _log_action(self, action: str, request_id: str, user_id: str, details: str):
        """Log workflow action."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "request_id": request_id,
            "user_id": user_id,
            "details": details
        }
        self.audit_trail.append(log_entry)
    
    def get_audit_trail(self, request_id: Optional[str] = None) -> List[Dict]:
        """Get audit trail of workflow actions."""
        if request_id:
            return [log for log in self.audit_trail if log["request_id"] == request_id]
        return self.audit_trail.copy()
    
    def get_request_status(self, request_id: str) -> Optional[Dict]:
        """Get current status of approval request."""
        request = self.requests.get(request_id)
        if not request:
            return None
        
        return {
            "request_id": request.request_id,
            "evidence_id": request.evidence_id,
            "status": request.status.value,
            "assigned_to": request.assigned_to,
            "approvals_count": len(request.approvals),
            "rejections_count": len(request.rejections),
            "created_at": request.created_at.isoformat(),
            "priority": request.priority
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create workflow
    workflow = ApprovalWorkflow()
    workflow.approval_chain["policy"] = ["hr_specialist", "hr_manager"]
    
    # Create approval request
    request = workflow.create_approval_request(
        evidence_id="policy_001",
        evidence_type="policy",
        requester_id="evidence_manager_1"
    )
    
    print(f"Created request: {request.request_id}")
    print(f"Status: {workflow.get_request_status(request.request_id)}")
    
    # Add approval
    workflow.submit_approval(
        request.request_id,
        "hr_specialist_1",
        EvidenceDecision.APPROVED_FOR_HR_USE,
        "Evidence is clear and supports HR decision"
    )
    
    print(f"\nAfter approval: {workflow.get_request_status(request.request_id)}")
