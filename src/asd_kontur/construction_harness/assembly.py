"""Deterministic context assembly and mandatory AI boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of

from .models import (
    ConstructionHarnessContextPack,
    CustomerRegulationAddition,
    HarnessError,
    HarnessErrorCode,
    HarnessMemorySnapshot,
    ProjectDefinition,
    RequiredEvidence,
    RequiredIDDocument,
    RequirementAuthority,
    WorkRequirementMatrix,
    WorkRequirementRow,
)

HARNESS_CONTRACT_VERSION = "1.8.0"


def apply_customer_regulation_additions(
    matrix: WorkRequirementMatrix,
    additions: tuple[CustomerRegulationAddition, ...],
) -> WorkRequirementMatrix:
    documents = {item.document_requirement_id for row in matrix.rows for item in row.documents}
    document_values = {
        item.document_requirement_id: item for row in matrix.rows for item in row.documents
    }
    revised_rows: list[WorkRequirementRow] = []
    for addition in additions:
        if (
            addition.organization_id != matrix.organization_id
            or addition.workspace_id != matrix.workspace_id
        ):
            raise HarnessError(
                HarnessErrorCode.SCOPE_VIOLATION,
                "Customer regulation cannot cross a workspace boundary",
            )
        if addition.document_requirement_id not in documents:
            raise HarnessError(
                HarnessErrorCode.REGULATORY_WEAKENING,
                "Customer overlay must target an existing normative requirement",
            )
        if (
            document_values[addition.document_requirement_id].authority_status
            is not RequirementAuthority.NORMATIVE_VERIFIED
        ):
            raise HarnessError(
                HarnessErrorCode.REGULATORY_WEAKENING,
                "Customer overlay requires an exact verified normative minimum",
            )
    by_document = {item.document_requirement_id: item for item in additions}
    for row in matrix.rows:
        revised_documents: list[RequiredIDDocument] = []
        revised_evidence = list(row.evidence)
        for document in row.documents:
            overlay = by_document.get(document.document_requirement_id)
            if overlay is None:
                revised_documents.append(document)
                continue
            revised_documents.append(
                RequiredIDDocument(
                    document_requirement_id=document.document_requirement_id,
                    document_type=document.document_type,
                    minimum_copies=document.minimum_copies + overlay.additional_copies,
                    form_edition=document.form_edition,
                    basis_refs=(
                        *document.basis_refs,
                        f"customer-regulation:{overlay.addition_id}:v{overlay.version}",
                    ),
                    authority_status=document.authority_status,
                )
            )
            revised_evidence.extend(
                RequiredEvidence(
                    evidence_requirement_id=deterministic_uuid(
                        f"customer-evidence:{overlay.addition_id}:{kind}"
                    ),
                    evidence_kind=kind,
                    source_fact_keys=(f"customer-regulation:{overlay.addition_id}",),
                )
                for kind in overlay.additional_evidence_kinds
            )
        revised_rows.append(
            WorkRequirementRow(
                row.work_package_id,
                row.controls,
                tuple(revised_evidence),
                tuple(revised_documents),
                row.normative_gaps,
            )
        )
    return WorkRequirementMatrix(
        matrix.matrix_id,
        matrix.version + 1,
        matrix.organization_id,
        matrix.workspace_id,
        matrix.project_definition_id,
        matrix.project_definition_version,
        tuple(revised_rows),
        tuple(item.addition_id for item in additions),
        matrix.rule_set_version_id,
        matrix.created_at,
    )


class ConstructionHarnessContextAssembler:
    """Merge workspace facts and the existing platform-memory layers deterministically."""

    def assemble(
        self,
        *,
        project: ProjectDefinition,
        matrix: WorkRequirementMatrix,
        memory: HarnessMemorySnapshot,
        customer_additions: tuple[CustomerRegulationAddition, ...] = (),
    ) -> ConstructionHarnessContextPack:
        if (project.organization_id, project.workspace_id) != (
            matrix.organization_id,
            matrix.workspace_id,
        ):
            raise HarnessError(HarnessErrorCode.SCOPE_VIOLATION, "Project and matrix scope differ")
        blocked_rules = {
            str(rule_id)
            for defect in memory.defects
            for rule_id in defect.blocking_rule_version_ids
        }
        safe_rules = tuple(
            ref for ref in memory.active_rule_version_refs if ref not in blocked_rules
        )
        evidence = tuple(
            dict.fromkeys(
                source
                for work in project.work_packages
                for source in (
                    *work.evidence,
                    *(item.evidence for item in work.quantities),
                    *(item.evidence for item in work.materials),
                    *(item.evidence for item in work.normative_references),
                )
            )
        )
        gaps = list(memory.gaps)
        for row in matrix.rows:
            gaps.extend(
                {"code": code, "work_package_id": str(row.work_package_id)}
                for code in row.normative_gaps
            )
        for defect in memory.defects:
            gaps.append(
                {
                    "code": HarnessErrorCode.KNOWLEDGE_DEFECT,
                    "defect_id": str(defect.defect_id),
                    "affected_reference": defect.affected_reference,
                }
            )
        workspace_fact_refs = tuple(
            f"project-characteristic:{item.characteristic_id}:v{item.version}"
            for item in project.characteristics
        )
        customer_addition_refs = tuple(
            f"customer-regulation:{item.addition_id}:v{item.version}" for item in customer_additions
        )
        consistency_defect_ids = tuple(item.defect_id for item in memory.defects)
        context_identity_material = digest_of(
            {
                "contract_version": HARNESS_CONTRACT_VERSION,
                "organization_id": project.organization_id,
                "workspace_id": project.workspace_id,
                "project_definition_ref": (project.project_definition_id, project.version),
                "matrix_ref": (matrix.matrix_id, matrix.version),
                "matrix_fingerprint": matrix.fingerprint,
                "workspace_fact_refs": workspace_fact_refs,
                "practice_intelligence_refs": memory.practice_intelligence_refs,
                "practice_playbook_refs": memory.practice_playbook_refs,
                "normative_edition_refs": memory.normative_edition_refs,
                "normative_provision_refs": memory.normative_provision_refs,
                "active_rule_version_refs": safe_rules,
                "customer_addition_refs": customer_addition_refs,
                "source_evidence": evidence,
                "knowledge_gaps": tuple(gaps),
                "consistency_defect_ids": consistency_defect_ids,
            }
        )
        return ConstructionHarnessContextPack(
            context_pack_id=deterministic_uuid(f"construction-context:{context_identity_material}"),
            contract_version=HARNESS_CONTRACT_VERSION,
            organization_id=project.organization_id,
            workspace_id=project.workspace_id,
            project_definition_ref=(project.project_definition_id, project.version),
            matrix_ref=(matrix.matrix_id, matrix.version),
            matrix_fingerprint=matrix.fingerprint,
            workspace_fact_refs=workspace_fact_refs,
            practice_intelligence_refs=memory.practice_intelligence_refs,
            practice_playbook_refs=memory.practice_playbook_refs,
            normative_edition_refs=memory.normative_edition_refs,
            normative_provision_refs=memory.normative_provision_refs,
            active_rule_version_refs=safe_rules,
            customer_addition_refs=customer_addition_refs,
            source_evidence=evidence,
            knowledge_gaps=tuple(gaps),
            consistency_defect_ids=consistency_defect_ids,
            assembled_at=max(project.created_at, matrix.created_at),
        )


@dataclass(frozen=True, slots=True)
class PreparedConstructionAIContext:
    context_pack_id: UUID
    context_pack_fingerprint: str
    model_profile_fingerprint: str
    evidence_pack: dict[str, Any]


class ConstructionAIContextGate:
    """Reject every substantive model call that bypasses Context Assembly."""

    def prepare(
        self,
        *,
        context_pack: ConstructionHarnessContextPack | None,
        model_profile_fingerprint: str,
    ) -> PreparedConstructionAIContext:
        if context_pack is None:
            raise HarnessError(
                HarnessErrorCode.CONTEXT_REQUIRED,
                "ID/construction AI execution requires ConstructionHarnessContextPack",
            )
        return PreparedConstructionAIContext(
            context_pack.context_pack_id,
            context_pack.fingerprint,
            model_profile_fingerprint,
            {
                "workspace_facts": context_pack.workspace_fact_refs,
                "methodological_practice": {
                    "guidance": context_pack.practice_intelligence_refs,
                    "playbooks": context_pack.practice_playbook_refs,
                },
                "normative_authority": {
                    "editions": context_pack.normative_edition_refs,
                    "provisions": context_pack.normative_provision_refs,
                },
                "deterministic_rules": context_pack.active_rule_version_refs,
                "customer_additions": context_pack.customer_addition_refs,
                "evidence": context_pack.source_evidence,
                "knowledge_gaps": context_pack.knowledge_gaps,
            },
        )
