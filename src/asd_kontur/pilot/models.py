"""Typed contracts for the bounded pilot workflow.

The values deliberately reference existing ProjectDefinition, matrix and source
locators.  They are a professional-result layer, not a second project model.
"""

from __future__ import annotations

from enum import StrEnum


class PilotMode(StrEnum):
    TENDER = "Tender"
    SUPPORT = "Support"
    AUDIT = "Audit"
    RESTORATION = "Restoration"


class PilotReviewAction(StrEnum):
    ACCEPT = "accepted"
    CORRECT = "corrected"
    EXCLUDE = "excluded"
    STATUS = "status_changed"
    COMMENT = "commented"


class PilotExportFormat(StrEnum):
    DOCX = "docx"
    PDF = "pdf"
    ZIP = "zip"


class PilotExportKind(StrEnum):
    DISAGREEMENT_PROTOCOL = "disagreement_protocol"
    CONTRACT_CHANGES = "contract_changes"
    REQUIREMENT_MATRIX = "requirement_matrix"
    ID_PACKAGE = "id_package"
    REGISTER = "register"
    AUDIT_REPORT = "audit_report"
    RECOVERY_PLAN = "recovery_plan"
    RECOVERED_DRAFTS = "recovered_drafts"
    WORKSPACE_RESULTS = "workspace_results"


MODE_EXPORTS: dict[PilotMode, tuple[PilotExportKind, ...]] = {
    PilotMode.TENDER: (
        PilotExportKind.DISAGREEMENT_PROTOCOL,
        PilotExportKind.CONTRACT_CHANGES,
    ),
    PilotMode.SUPPORT: (
        PilotExportKind.REQUIREMENT_MATRIX,
        PilotExportKind.ID_PACKAGE,
        PilotExportKind.REGISTER,
    ),
    PilotMode.AUDIT: (PilotExportKind.AUDIT_REPORT,),
    PilotMode.RESTORATION: (
        PilotExportKind.RECOVERY_PLAN,
        PilotExportKind.RECOVERED_DRAFTS,
    ),
}
