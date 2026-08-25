"""Deterministic context assembly and mandatory ID-related VLM gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.knowledge.gateway import (
    GUIDANCE_CONTRACT_VERSION,
    GUIDANCE_SCHEMA_ID,
    GatewayContext,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    KnowledgeGateway,
)

from .models import (
    ContextAssemblyPolicy,
    IDPracticeContextPack,
    PracticeContextStatus,
)


@dataclass(frozen=True, slots=True)
class IDPracticeContextRequest:
    context_request_id: UUID
    mode: str
    purpose: str
    intent: str
    query: str
    practice_guide_edition_id: UUID
    document_type: str | None = None
    form_type: str | None = None
    field: str | None = None
    work_type: str | None = None
    rd_section: str | None = None
    construction_stage: str | None = None
    control_operation: str | None = None
    evidence_requirement: str | None = None
    package_process: str | None = None
    workspace_fact_refs: tuple[str, ...] = ()
    deterministic_rule_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.mode or not self.purpose or not self.intent or not self.query.strip():
            raise ValueError("ID practice context request requires mode, purpose, intent and query")


@dataclass(frozen=True, slots=True)
class PreparedIDVlmContext:
    context_pack_id: UUID
    context_pack_fingerprint: str
    context_status: PracticeContextStatus
    model_profile_fingerprint: str
    evidence_document: dict[str, Any]


class IDPracticeContextAssembler:
    """Select exact canonical practice units before any ID-related model call."""

    def __init__(self, gateway: KnowledgeGateway, policy: ContextAssemblyPolicy) -> None:
        self._gateway = gateway
        self._policy = policy

    def assemble(
        self,
        *,
        request: IDPracticeContextRequest,
        gateway_context: GatewayContext,
        lexical_version_id: UUID,
    ) -> IDPracticeContextPack:
        if request.mode not in self._policy.allowed_modes:
            return self._degraded(
                request,
                PracticeContextStatus.KNOWLEDGE_INCOMPLETE,
                "context_mode_not_allowed",
            )
        if request.purpose not in self._policy.allowed_purposes:
            return self._degraded(
                request,
                PracticeContextStatus.KNOWLEDGE_INCOMPLETE,
                "context_purpose_not_allowed",
            )
        if request.practice_guide_edition_id != self._policy.practice_guide_edition_id:
            return self._degraded(
                request,
                PracticeContextStatus.EDITION_MISMATCH,
                "edition_mismatch",
            )
        payload: dict[str, object] = {
            "query": request.query,
            "intent": request.intent,
            "lexical_version_id": str(lexical_version_id),
            "practice_guide_edition_id": str(request.practice_guide_edition_id),
            "context_assembly_policy_id": str(self._policy.policy_id),
            "context_assembly_policy_version": self._policy.version,
            "max_intelligence_units": self._policy.max_intelligence_units,
            "max_playbooks": self._policy.max_playbooks,
            "mode": request.mode,
            "purpose": request.purpose,
        }
        for key, value in (
            ("document_type", request.document_type),
            ("form_type", request.form_type),
            ("field", request.field),
            ("work_type", request.work_type),
            ("rd_section", request.rd_section),
            ("construction_stage", request.construction_stage),
            ("control_operation", request.control_operation),
            ("evidence_requirement", request.evidence_requirement),
            ("package_process", request.package_process),
        ):
            if value:
                payload[key] = value
        response = self._gateway.invoke(
            GatewayRequest(
                "knowledge.get_id_task_guidance",
                GUIDANCE_CONTRACT_VERSION,
                GUIDANCE_SCHEMA_ID,
                GUIDANCE_CONTRACT_VERSION,
                payload,
            ),
            gateway_context,
        )
        return self._from_gateway(request, response)

    def _from_gateway(
        self, request: IDPracticeContextRequest, response: GatewayResponse
    ) -> IDPracticeContextPack:
        units = response.result.get("practice_intelligence")
        playbooks = response.result.get("practice_playbooks")
        unit_values = (
            tuple(item for item in units if isinstance(item, dict))
            if isinstance(units, list)
            else ()
        )
        playbook_values = (
            tuple(item for item in playbooks if isinstance(item, dict))
            if isinstance(playbooks, list)
            else ()
        )
        returned_edition = response.result.get("practice_guide_edition_id")
        if (
            returned_edition is not None
            and UUID(str(returned_edition)) != request.practice_guide_edition_id
        ):
            return self._degraded(
                request,
                PracticeContextStatus.EDITION_MISMATCH,
                "edition_mismatch",
            )
        if response.status is GatewayStatus.EDITION_MISMATCH:
            status = PracticeContextStatus.EDITION_MISMATCH
        elif response.evidence_pack.conflicts:
            status = PracticeContextStatus.GUIDANCE_NORMATIVE_CONFLICT
        elif response.status is GatewayStatus.INDEX_UNAVAILABLE:
            status = PracticeContextStatus.MEMORY_UNAVAILABLE
        elif (
            response.status is not GatewayStatus.OK
            or not unit_values
            or not response.evidence_pack.evidence
        ):
            status = PracticeContextStatus.KNOWLEDGE_INCOMPLETE
        else:
            status = PracticeContextStatus.OK
        gaps = response.evidence_pack.gaps
        conflicts = response.evidence_pack.conflicts
        if status is not PracticeContextStatus.OK and not (gaps or conflicts):
            gaps = ({"code": status.value},)
        evidence = response.evidence_pack.evidence
        unit_refs = tuple(
            (UUID(str(item["intelligence_unit_id"])), int(item["version"])) for item in unit_values
        )
        playbook_refs = tuple(
            (UUID(str(item["playbook_id"])), int(item["version"]))
            for item in playbook_values
            if item.get("playbook_id") is not None and item.get("version") is not None
        )
        pack_id = deterministic_uuid(
            f"id-practice-context-pack:{request.context_request_id}:{self._policy.fingerprint}:"
            f"{response.status.value}:{','.join(str(item[0]) for item in unit_refs)}"
        )
        composition = response.result.get("authority_composition")
        normative: tuple[dict[str, Any], ...] = ()
        if isinstance(composition, dict):
            normative_part = composition.get("normative_authority")
            if isinstance(normative_part, dict):
                refs = normative_part.get("references")
                if isinstance(refs, (list, tuple)):
                    normative = tuple(item for item in refs if isinstance(item, dict))
        return IDPracticeContextPack(
            context_pack_id=pack_id,
            context_request_id=request.context_request_id,
            policy_id=self._policy.policy_id,
            policy_version=self._policy.version,
            practice_guide_edition_id=request.practice_guide_edition_id,
            status=status,
            intelligence_unit_refs=unit_refs,
            playbook_refs=playbook_refs,
            source_version_ids=tuple(
                dict.fromkeys(UUID(item.source_version_id) for item in evidence)
            ),
            source_locators=tuple(dict.fromkeys(item.structural_unit_locator for item in evidence)),
            normative_requirements=normative,
            practice_advice=unit_values,
            workspace_fact_refs=request.workspace_fact_refs,
            deterministic_rule_refs=request.deterministic_rule_refs,
            gaps=gaps,
            conflicts=conflicts,
            uncertainties=response.evidence_pack.uncertainties,
            assembled_at=datetime.now(UTC),
        )

    def _degraded(
        self,
        request: IDPracticeContextRequest,
        status: PracticeContextStatus,
        code: str,
    ) -> IDPracticeContextPack:
        return IDPracticeContextPack(
            context_pack_id=deterministic_uuid(
                f"id-practice-context-pack:{request.context_request_id}:{self._policy.fingerprint}:{code}"
            ),
            context_request_id=request.context_request_id,
            policy_id=self._policy.policy_id,
            policy_version=self._policy.version,
            practice_guide_edition_id=request.practice_guide_edition_id,
            status=status,
            intelligence_unit_refs=(),
            playbook_refs=(),
            source_version_ids=(),
            source_locators=(),
            normative_requirements=(),
            practice_advice=(),
            workspace_fact_refs=request.workspace_fact_refs,
            deterministic_rule_refs=request.deterministic_rule_refs,
            gaps=({"code": code},),
            conflicts=(),
            uncertainties=(),
            assembled_at=datetime.now(UTC),
        )


class IDRelatedVlmContextGate:
    """Refuse an ID-related VLM call that did not pass deterministic assembly."""

    @staticmethod
    def prepare(
        *,
        context_pack: IDPracticeContextPack | None,
        model_profile_fingerprint: str,
    ) -> PreparedIDVlmContext:
        if context_pack is None:
            raise PermissionError("id_context_assembly_required")
        if context_pack.status not in {
            PracticeContextStatus.OK,
            PracticeContextStatus.KNOWLEDGE_INCOMPLETE,
        }:
            raise PermissionError(context_pack.status.value)
        if context_pack.status is PracticeContextStatus.KNOWLEDGE_INCOMPLETE and (
            not context_pack.intelligence_unit_refs
            or not context_pack.source_version_ids
            or not context_pack.source_locators
            or not context_pack.practice_advice
        ):
            raise PermissionError(PracticeContextStatus.KNOWLEDGE_INCOMPLETE.value)
        if not model_profile_fingerprint.startswith("sha256:"):
            raise ValueError("ID-related VLM execution requires an exact model profile")
        return PreparedIDVlmContext(
            context_pack.context_pack_id,
            context_pack.fingerprint,
            context_pack.status,
            model_profile_fingerprint,
            {
                "context_status": context_pack.status.value,
                "authority_layer": context_pack.authority_layer.value,
                "practice_guide_edition_id": str(context_pack.practice_guide_edition_id),
                "policy": {
                    "policy_id": str(context_pack.policy_id),
                    "version": context_pack.policy_version,
                },
                "practice_intelligence": list(context_pack.practice_advice),
                "normative_requirements": list(context_pack.normative_requirements),
                "workspace_fact_refs": list(context_pack.workspace_fact_refs),
                "deterministic_rule_refs": list(context_pack.deterministic_rule_refs),
                "source_versions": [str(value) for value in context_pack.source_version_ids],
                "citations": list(context_pack.source_locators),
                "gaps": list(context_pack.gaps),
                "conflicts": list(context_pack.conflicts),
                "uncertainties": list(context_pack.uncertainties),
            },
        )
