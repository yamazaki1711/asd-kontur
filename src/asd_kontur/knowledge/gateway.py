"""Stable internal Knowledge Tool Gateway without transport or direct SQL exposure."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from .errors import KnowledgeError, KnowledgeErrorCode

SUPPORTED_CONTRACT_VERSION = "0.1.0"
SUPPORTED_SCHEMA_ID = "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge"
GUIDANCE_CONTRACT_VERSION = "1.6.0"
GUIDANCE_SCHEMA_ID = "urn:asd-kontur:contracts:v1.6:schema:practice-intelligence"
NTD_CONTRACT_VERSION = "1.7.0"
NTD_SCHEMA_ID = "urn:asd-kontur:contracts:v1.7:schema:normative-knowledge"
BASE_TOOLS = frozenset(
    {
        "knowledge.search",
        "knowledge.get_source_fragment",
        "knowledge.get_applicable_rules",
        "knowledge.trace_assertion",
        "knowledge.explain_conflict",
        "knowledge.get_required_documents",
    }
)
GUIDANCE_TOOLS = frozenset(
    {
        "knowledge.get_id_guidance",
        "knowledge.get_form_guidance",
        "knowledge.get_field_guidance",
        "knowledge.trace_guidance",
        "knowledge.explain_guidance_conflict",
        "knowledge.get_id_task_guidance",
        "knowledge.get_practice_playbook",
    }
)
NTD_TOOLS = frozenset(
    {
        "knowledge.resolve_ntd",
        "knowledge.get_ntd_document",
        "knowledge.get_ntd_edition",
        "knowledge.get_ntd_provision",
        "knowledge.search_ntd",
        "knowledge.get_ntd_evidence_pack",
        "knowledge.get_practice_ntd_alignment",
    }
)
TOOLS = BASE_TOOLS | GUIDANCE_TOOLS | NTD_TOOLS


class GatewayStatus(StrEnum):
    OK = "ok"
    NO_RESULT = "no_result"
    INDEX_UNAVAILABLE = "index_unavailable"
    KNOWLEDGE_INCOMPLETE = "knowledge_incomplete"
    EDITION_AMBIGUOUS = "edition_ambiguous"
    EDITION_MISMATCH = "edition_mismatch"
    GUIDANCE_NORMATIVE_CONFLICT = "guidance_normative_conflict"
    NORMATIVE_CONFLICT = "normative_conflict"
    KNOWLEDGE_GAP = "knowledge_gap"
    APPLICABILITY_INDETERMINATE = "applicability_indeterminate"


@dataclass(frozen=True, slots=True)
class GatewayContext:
    actor_identity_id: str
    capability: str
    purpose: str
    correlation_id: UUID
    organization_id: UUID | None = None
    workspace_id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.organization_id is None) != (self.workspace_id is None):
            raise KnowledgeError(
                KnowledgeErrorCode.SCOPE_VIOLATION,
                "Organization and workspace scope must be supplied together.",
            )


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    tool: str
    contract_version: str
    schema_id: str
    schema_version: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_link_id: str
    source_version_id: str
    edition_id: str | None
    structural_unit_locator: str
    content_digest: str
    access_reference: str
    authority_layer: str = "normative_or_canonical_knowledge"


@dataclass(frozen=True, slots=True)
class EvidencePack:
    evidence: tuple[EvidenceItem, ...]
    applicability: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    gaps: tuple[dict[str, Any], ...]
    uncertainties: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    tool: str
    contract_version: str
    status: GatewayStatus
    result: dict[str, Any]
    evidence_pack: EvidencePack


class KnowledgeQueryPort(Protocol):
    def execute(
        self, tool: str, payload: dict[str, Any], context: GatewayContext
    ) -> GatewayResponse: ...


class KnowledgeAuditPort(Protocol):
    def record(
        self,
        *,
        context: GatewayContext,
        tool: str,
        status: GatewayStatus | str,
        evidence_count: int,
    ) -> None: ...


class KnowledgeGateway:
    def __init__(self, query: KnowledgeQueryPort, audit: KnowledgeAuditPort) -> None:
        self._query = query
        self._audit = audit

    def invoke(self, request: GatewayRequest, context: GatewayContext) -> GatewayResponse:
        if request.tool not in TOOLS:
            raise KnowledgeError(
                KnowledgeErrorCode.CONTRACT_VERSION_UNSUPPORTED,
                "Unknown Knowledge Tool contract.",
            )
        if request.tool in GUIDANCE_TOOLS:
            expected_contract = GUIDANCE_CONTRACT_VERSION
            expected_schema = GUIDANCE_SCHEMA_ID
        elif request.tool in NTD_TOOLS:
            expected_contract = NTD_CONTRACT_VERSION
            expected_schema = NTD_SCHEMA_ID
        else:
            expected_contract = SUPPORTED_CONTRACT_VERSION
            expected_schema = SUPPORTED_SCHEMA_ID
        if (
            request.contract_version != expected_contract
            or request.schema_version != expected_contract
            or request.schema_id != expected_schema
        ):
            raise KnowledgeError(
                KnowledgeErrorCode.CONTRACT_VERSION_UNSUPPORTED,
                "Knowledge Tool requests must pin the exact supported contract version.",
            )
        if context.capability != f"{request.tool}.invoke":
            self._audit.record(
                context=context,
                tool=request.tool,
                status="access_denied",
                evidence_count=0,
            )
            raise KnowledgeError(
                KnowledgeErrorCode.ACCESS_DENIED,
                "The identity lacks the exact Knowledge Tool capability.",
            )
        response = self._query.execute(request.tool, request.payload, context)
        self._audit.record(
            context=context,
            tool=request.tool,
            status=response.status,
            evidence_count=len(response.evidence_pack.evidence),
        )
        return response
