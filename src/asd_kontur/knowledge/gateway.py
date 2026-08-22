"""Stable internal Knowledge Tool Gateway without transport or direct SQL exposure."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from .errors import KnowledgeError, KnowledgeErrorCode

SUPPORTED_CONTRACT_VERSION = "0.1.0"
SUPPORTED_SCHEMA_ID = "urn:asd-kontur:contracts:v0.1:schema:rules-knowledge"
TOOLS = frozenset(
    {
        "knowledge.search",
        "knowledge.get_source_fragment",
        "knowledge.get_applicable_rules",
        "knowledge.trace_assertion",
        "knowledge.explain_conflict",
        "knowledge.get_required_documents",
    }
)


class GatewayStatus(StrEnum):
    OK = "ok"
    NO_RESULT = "no_result"
    INDEX_UNAVAILABLE = "index_unavailable"
    KNOWLEDGE_INCOMPLETE = "knowledge_incomplete"
    EDITION_AMBIGUOUS = "edition_ambiguous"


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
        if (
            request.contract_version != SUPPORTED_CONTRACT_VERSION
            or request.schema_version != SUPPORTED_CONTRACT_VERSION
            or request.schema_id != SUPPORTED_SCHEMA_ID
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
