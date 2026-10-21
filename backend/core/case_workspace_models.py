"""LEAMSS Secure Case Workspace Models & Abstractions.

Defines schemas and constants for:
- Case-centred workspaces
- Multi-application registers (Skills Assessments, EOIs, State Nominations/ROIs, Visa Applications)
- Granular temporary access grants with expiration and revocation
- Document sensitivity classifications (Standard, Identity/Sensitive, Highly Restricted)
- Credential vault abstraction (zero plaintext passwords in CRM)
- Sensitive identifier masking (TRN, EOI ID, Passports)
"""
from __future__ import annotations

import enum
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# 1. Enums & Classifications
# ─────────────────────────────────────────────────────────────────────────────

class DocumentSensitivityTier(str, enum.Enum):
    STANDARD = "standard"                     # Resumes, brochures, general forms
    SENSITIVE_IDENTITY = "sensitive_identity" # Passports, National IDs, PCC, Medicals, Financials
    HIGHLY_RESTRICTED = "highly_restricted"   # Legal affidavits, adoption, protection claims


class ApplicationType(str, enum.Enum):
    SKILLS_ASSESSMENT = "skills_assessment"
    EOI = "eoi"
    ROI_NOMINATION = "roi_nomination"
    VISA_LODGEMENT = "visa_lodgement"
    OTHER = "other"


class ApplicationStatus(str, enum.Enum):
    DRAFT = "draft"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    IN_PROGRESS = "in_progress"
    ADDITIONAL_INFO_REQUESTED = "additional_info_requested"
    INVITED = "invited"
    NOMINATED = "nominated"
    APPROVED = "approved"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class WorkspaceLifecycleState(str, enum.Enum):
    INTAKE = "intake"
    ASSESSMENT = "assessment"
    DOCUMENT_GATHERING = "document_gathering"
    LODGEMENT_PREPARATION = "lodgement_preparation"
    LODGED_AWAITING_DECISION = "lodged_awaiting_decision"
    DECISION_RECEIVED = "decision_received"
    POST_DECISION = "post_decision"
    ARCHIVED = "archived"


class AccessGrantRole(str, enum.Enum):
    REVIEWER = "reviewer"
    TEMPORARY_CASE_MANAGER = "temporary_case_manager"
    TEMPORARY_MANAGER = "temporary_manager"
    AUDITOR = "auditor"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class CaseApplicationCreate(BaseModel):
    case_id: Optional[str] = None
    client_id: Optional[str] = None
    application_type: ApplicationType
    country: str = "AU"
    authority_or_state: str = Field(..., description="e.g. ACS, VETASSESS, NSW, VIC, DHA, IRCC")
    subclass_or_stream: Optional[str] = Field(None, description="e.g. 189, 190, 491, 186, Express Entry")
    applicant_type: Literal["primary", "dependant", "spouse"] = "primary"
    applicant_name: Optional[str] = None
    reference_identifier: Optional[str] = Field(None, description="Sensitive identifier (e.g. TRN, EOI ID)")
    status: ApplicationStatus = ApplicationStatus.DRAFT
    status_source: Literal["manual_entry", "official_correspondence", "portal_extract"] = "manual_entry"
    submission_date: Optional[str] = None
    points_claimed: Optional[int] = None
    responsible_staff_id: Optional[str] = None
    next_action: Optional[str] = None
    deadline: Optional[str] = None
    notes: Optional[str] = None


class CaseApplicationUpdate(BaseModel):
    authority_or_state: Optional[str] = None
    subclass_or_stream: Optional[str] = None
    applicant_type: Optional[Literal["primary", "dependant", "spouse"]] = None
    applicant_name: Optional[str] = None
    reference_identifier: Optional[str] = None
    status: Optional[ApplicationStatus] = None
    status_source: Optional[Literal["manual_entry", "official_correspondence", "portal_extract"]] = None
    submission_date: Optional[str] = None
    points_claimed: Optional[int] = None
    responsible_staff_id: Optional[str] = None
    next_action: Optional[str] = None
    deadline: Optional[str] = None
    notes: Optional[str] = None


class CaseAccessGrantCreate(BaseModel):
    case_id: Optional[str] = None
    user_id: str
    role_granted: AccessGrantRole = AccessGrantRole.REVIEWER
    duration_hours: Optional[int] = Field(24, ge=1, le=720, description="Grant duration in hours (default 24h, max 30d)")
    expires_in_hours: Optional[int] = None
    reason: str = Field(..., min_length=3, description="Audited business justification for temporary access")
    permissions: List[str] = Field(
        default=["case.view", "document.preview"],
        description="Explicit granted permissions",
    )
    resource_scope: str = Field(default="case", description="Scope of grant: 'case', 'application', or 'document'")
    resource_id: Optional[str] = Field(default=None, description="Optional specific application or document ID")


class CaseReassignRequest(BaseModel):
    new_case_manager_id: str
    reason: Optional[str] = Field(default=None, description="Reason for transferring primary case responsibility")


class SensitiveAccessRequestCreate(BaseModel):
    case_id: Optional[str] = None
    action: str = Field(..., description="Action requested: 'identifier.reveal', 'credential.access', or 'document.preview'")
    resource_id: str = Field(..., description="Target application, document, or credential ID")
    resource_name: Optional[str] = Field(None, description="Human readable label for the requested resource")
    reason: str = Field(..., min_length=5, description="Business justification for requesting sensitive access")
    requested_duration_hours: int = Field(24, ge=1, le=168, description="Requested access duration in hours (max 7 days)")


class SensitiveAccessRequestDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    notes: Optional[str] = Field(None, description="Approver comments or rationale")


class IdentifierRevealRequest(BaseModel):
    model_config = {"extra": "ignore"}
    application_id: Optional[str] = None
    document_id: Optional[str] = None
    case_id: Optional[str] = None
    reason: str = Field(..., min_length=3, description="Audited justification for revealing full unmasked identifier")


class CredentialVaultRegister(BaseModel):
    model_config = {"extra": "ignore"}
    case_id: Optional[str] = None
    portal_name: str = Field(..., description="e.g. SkillSelect, ImmiAccount, VETASSESS Portal")
    portal_url: Optional[str] = None
    username_or_id: str
    secret_value: str = Field(..., min_length=1, description="Secret submitted to vault adapter (will NOT be stored in cleartext)")
    notes: Optional[str] = None


class CredentialAccessRequest(BaseModel):
    model_config = {"extra": "ignore"}
    credential_id: Optional[str] = None
    vault_id: Optional[str] = None
    case_id: Optional[str] = None
    reason: str = Field(..., min_length=3, description="Audited justification for retrieving temporary credential access")



# ─────────────────────────────────────────────────────────────────────────────
# 3. Helpers: Identifier Masking & Normalization
# ─────────────────────────────────────────────────────────────────────────────

def mask_identifier(val: Optional[str]) -> str:
    """Mask a sensitive identifier leaving only last 4 characters visible.
    
    Examples:
        'DHA-9876543210' -> 'DHA-******3210'
        'E01234567'      -> '*****4567'
        '123'            -> '***'
    """
    if not val:
        return "—"
    s = str(val).strip()
    if len(s) <= 4:
        return "*" * len(s)
    prefix_len = 0
    if "-" in s:
        parts = s.split("-", 1)
        prefix = parts[0] + "-"
        remainder = parts[1]
        if len(remainder) <= 4:
            return prefix + ("*" * len(remainder))
        return prefix + ("*" * (len(remainder) - 4)) + remainder[-4:]
    return ("*" * (len(s) - 4)) + s[-4:]


def mask_email(email: Optional[str]) -> str:
    """Mask an email address for safe display."""
    if not email or "@" not in email:
        return "—"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + ("*" * (len(local) - 2)) + local[-1]
    return f"{masked_local}@{domain}"
