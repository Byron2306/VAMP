"""Role-Based Access Control (RBAC) - Phase 4 Authorization Layer.

Implements deterministic, fine-grained access control for evidence approval workflows.
Supports role hierarchies, permission caching, and audit trails.
"""

from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging
from abc import ABC, abstractmethod


class Role(Enum):
    """User roles in the HR approval workflow."""
    VIEWER = "viewer"              # Can only read evidence
    EVIDENCE_MANAGER = "evidence_manager"  # Can manage evidence processing
    HR_SPECIALIST = "hr_specialist"      # Can approve evidence for HR use
    HR_MANAGER = "hr_manager"          # Can approve and override decisions
    COMPLIANCE_OFFICER = "compliance_officer"  # Can audit and enforce policies
    SYSTEM_ADMIN = "system_admin"       # Full access


class Permission(Enum):
    """Fine-grained permissions."""
    # Evidence operations
    READ_EVIDENCE = "read_evidence"
    PROCESS_EVIDENCE = "process_evidence"
    APPROVE_EVIDENCE = "approve_evidence"
    REJECT_EVIDENCE = "reject_evidence"
    
    # Workflow operations
    VIEW_WORKFLOW = "view_workflow"
    MODIFY_WORKFLOW = "modify_workflow"
    
    # HR operations
    VIEW_HR_DATA = "view_hr_data"
    APPROVE_HR_DECISION = "approve_hr_decision"
    OVERRIDE_DECISION = "override_decision"
    
    # Compliance operations
    AUDIT_EVIDENCE = "audit_evidence"
    ENFORCE_POLICY = "enforce_policy"
    
    # Admin operations
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_AUDIT_LOG = "view_audit_log"


@dataclass
class User:
    """User with role and permission assignments."""
    user_id: str
    username: str
    email: str
    roles: Set[Role] = field(default_factory=set)
    custom_permissions: Set[Permission] = field(default_factory=set)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    
    def add_role(self, role: Role):
        """Add a role to the user."""
        self.roles.add(role)
    
    def remove_role(self, role: Role):
        """Remove a role from the user."""
        self.roles.discard(role)
    
    def has_role(self, role: Role) -> bool:
        """Check if user has a specific role."""
        return role in self.roles


class RolePermissionMapper:
    """Maps roles to their default permissions."""
    
    ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
        Role.VIEWER: {
            Permission.READ_EVIDENCE,
            Permission.VIEW_WORKFLOW,
            Permission.VIEW_HR_DATA,
        },
        Role.EVIDENCE_MANAGER: {
            Permission.READ_EVIDENCE,
            Permission.PROCESS_EVIDENCE,
            Permission.VIEW_WORKFLOW,
            Permission.VIEW_HR_DATA,
        },
        Role.HR_SPECIALIST: {
            Permission.READ_EVIDENCE,
            Permission.PROCESS_EVIDENCE,
            Permission.APPROVE_EVIDENCE,
            Permission.REJECT_EVIDENCE,
            Permission.VIEW_WORKFLOW,
            Permission.VIEW_HR_DATA,
            Permission.APPROVE_HR_DECISION,
        },
        Role.HR_MANAGER: {
            Permission.READ_EVIDENCE,
            Permission.PROCESS_EVIDENCE,
            Permission.APPROVE_EVIDENCE,
            Permission.REJECT_EVIDENCE,
            Permission.VIEW_WORKFLOW,
            Permission.MODIFY_WORKFLOW,
            Permission.VIEW_HR_DATA,
            Permission.APPROVE_HR_DECISION,
            Permission.OVERRIDE_DECISION,
        },
        Role.COMPLIANCE_OFFICER: {
            Permission.READ_EVIDENCE,
            Permission.VIEW_WORKFLOW,
            Permission.VIEW_HR_DATA,
            Permission.AUDIT_EVIDENCE,
            Permission.ENFORCE_POLICY,
            Permission.VIEW_AUDIT_LOG,
        },
        Role.SYSTEM_ADMIN: set(Permission),  # All permissions
    }
    
    @classmethod
    def get_permissions_for_role(cls, role: Role) -> Set[Permission]:
        """Get all permissions for a role."""
        return cls.ROLE_PERMISSIONS.get(role, set()).copy()
    
    @classmethod
    def get_permissions_for_user(cls, user: User) -> Set[Permission]:
        """Get all permissions for a user based on their roles."""
        permissions = set()
        for role in user.roles:
            permissions.update(cls.get_permissions_for_role(role))
        permissions.update(user.custom_permissions)
        return permissions


@dataclass
class AccessContext:
    """Context for access control decision."""
    user: User
    required_permission: Permission
    resource_id: Optional[str] = None
    action: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class AccessControl:
    """Enforces RBAC policies with audit trails."""
    
    def __init__(self):
        self.logger = logging.getLogger("AccessControl")
        self.permission_cache: Dict[str, Set[Permission]] = {}
        self.audit_log: List[Dict] = []
    
    def check_permission(self, context: AccessContext) -> bool:
        """Check if user has required permission.
        
        Args:
            context: Access context with user and permission details
            
        Returns:
            True if access is granted, False otherwise
        """
        # Check if user is active
        if not context.user.is_active:
            self._log_access_denial(context, "User is inactive")
            return False
        
        # Get cached permissions or compute them
        if context.user.user_id not in self.permission_cache:
            self.permission_cache[context.user.user_id] = RolePermissionMapper.get_permissions_for_user(context.user)
        
        user_permissions = self.permission_cache[context.user.user_id]
        has_permission = context.required_permission in user_permissions
        
        if has_permission:
            self._log_access_grant(context)
        else:
            self._log_access_denial(context, "Permission denied")
        
        return has_permission
    
    def check_permissions(self, context: AccessContext, required_permissions: Set[Permission]) -> bool:
        """Check if user has ALL required permissions."""
        for permission in required_permissions:
            context.required_permission = permission
            if not self.check_permission(context):
                return False
        return True
    
    def check_any_permission(self, context: AccessContext, required_permissions: Set[Permission]) -> bool:
        """Check if user has ANY of the required permissions."""
        for permission in required_permissions:
            context.required_permission = permission
            if self.check_permission(context):
                return True
        return False
    
    def _log_access_grant(self, context: AccessContext):
        """Log successful access."""
        log_entry = {
            "timestamp": context.timestamp.isoformat(),
            "user_id": context.user.user_id,
            "action": "GRANT",
            "permission": context.required_permission.value,
            "resource_id": context.resource_id,
        }
        self.audit_log.append(log_entry)
        self.logger.info(f"Access granted: {context.user.user_id} - {context.required_permission.value}")
    
    def _log_access_denial(self, context: AccessContext, reason: str):
        """Log access denial."""
        log_entry = {
            "timestamp": context.timestamp.isoformat(),
            "user_id": context.user.user_id,
            "action": "DENY",
            "permission": context.required_permission.value,
            "resource_id": context.resource_id,
            "reason": reason,
        }
        self.audit_log.append(log_entry)
        self.logger.warning(f"Access denied: {context.user.user_id} - {context.required_permission.value} - {reason}")
    
    def invalidate_user_cache(self, user_id: str):
        """Invalidate cached permissions for a user."""
        self.permission_cache.pop(user_id, None)
    
    def get_audit_trail(self, user_id: Optional[str] = None) -> List[Dict]:
        """Get audit trail of access attempts."""
        if user_id:
            return [log for log in self.audit_log if log["user_id"] == user_id]
        return self.audit_log.copy()


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Create users with different roles
    viewer = User("user1", "john_viewer", "john@example.com")
    viewer.add_role(Role.VIEWER)
    
    hr_specialist = User("user2", "jane_hr", "jane@example.com")
    hr_specialist.add_role(Role.HR_SPECIALIST)
    
    # Create access control
    ac = AccessControl()
    
    # Test access
    context_viewer = AccessContext(
        user=viewer,
        required_permission=Permission.READ_EVIDENCE
    )
    
    context_admin = AccessContext(
        user=hr_specialist,
        required_permission=Permission.APPROVE_EVIDENCE
    )
    
    print(f"Viewer can read evidence: {ac.check_permission(context_viewer)}")
    print(f"HR Specialist can approve evidence: {ac.check_permission(context_admin)}")
    
    # Check audit trail
    print("\nAudit Trail:")
    for log in ac.get_audit_trail():
        print(log)
