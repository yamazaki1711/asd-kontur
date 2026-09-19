"""PostgreSQL persistence for workspace-owned document understanding."""

# ruff: noqa: E501 - long SQL fragments are kept contiguous for auditability.

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import ClaimedJob, semantic_digest
from asd_kontur.domain import deterministic_uuid
from asd_kontur.ntd.pd_rd import (
    PdRdProfileContext,
    evaluate_pd_rd_requirements,
    load_spds_corpus_denominator,
)

from .models import (
    PROJECT_EXTRACTION_PROFILE_VERSION,
    UNDERSTANDING_PROFILE_VERSION,
    WORK_EXTRACTION_PROFILE_VERSION,
    DocumentRole,
    ExactLocator,
    LayoutElement,
    MaterialCandidate,
    ProjectFieldCandidate,
    ProjectUnderstandingSnapshot,
    QuantityCandidate,
    ReconciliationDefect,
    RoleCandidate,
    RoleDecision,
    StructureIdentityCandidate,
    StructureNodeCandidate,
    StructureRelationshipCandidate,
    WorkTypeCandidate,
)
from .native import NativeDocument
from .ocr import OcrAdapterResult
from .semantic import StructuredCandidates
from .work_packages import consolidate_work_package_candidates


def _identity_observation_group_key(normalized_name: str) -> str:
    """Return a Qwen-comparison key without deciding entity identity.

    Document conventions commonly vary only by spacing, punctuation or a
    hyphen in the same facility label.  Those aliases need to reach the Qwen
    reconciliation prompt together, but this key is never persisted as a
    canonical name and never merges nodes on its own.
    """

    return re.sub(r"[^\w]+", "", normalized_name.casefold(), flags=re.UNICODE)


class UnderstandingPersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IndustrialUnderstandingRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def document_identity(self, claimed: ClaimedJob) -> tuple[UUID, int, UUID]:
        return (
            self._document_id(claimed),
            self._document_version(claimed),
            self._source_version_id(claimed),
        )

    def record_stage_result(
        self,
        claimed: ClaimedJob,
        *,
        stage_kind: str,
        profile_version: str,
        output_manifest: dict[str, Any],
        terminal_status: str = "complete",
        typed_failure_code: str | None = None,
    ) -> UUID:
        output_digest = semantic_digest(output_manifest)
        stage_result_id = deterministic_uuid(
            f"understanding-stage:{claimed.job_id}:{stage_kind}:{output_digest}"
        )
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_understanding_stage_results "
                    "(organization_id,workspace_id,stage_result_id,job_id,document_id,document_version,"
                    "source_version_id,stage_kind,profile_version,input_digest,output_manifest,output_digest,"
                    "terminal_status,typed_failure_code) VALUES "
                    "(:o,:w,:result,:job,:document,:version,:source,:stage,:profile,:input,"
                    "CAST(:manifest AS jsonb),:output,:status,:failure) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "result": stage_result_id,
                    "job": claimed.job_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                    "source": self._source_version_id(claimed),
                    "stage": stage_kind,
                    "profile": profile_version,
                    "input": claimed.input_digest,
                    "manifest": _json(output_manifest),
                    "output": output_digest,
                    "status": terminal_status,
                    "failure": typed_failure_code,
                },
            )
        return stage_result_id

    def load_accepted_engineering_batches(
        self, claimed: ClaimedJob, *, profile_version: str
    ) -> dict[str, dict[str, object]]:
        with self._session(claimed) as session:
            rows = session.execute(
                sa.text(
                    "SELECT batch_digest, output_manifest FROM workspace.engineering_extraction_batches "
                    "WHERE organization_id=:o AND workspace_id=:w AND source_version_id=:source "
                    "AND profile_version=:profile AND terminal_status='accepted'"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "source": self._source_version_id(claimed),
                    "profile": profile_version,
                },
            ).mappings()
            return {
                str(row["batch_digest"]): dict(row["output_manifest"])
                for row in rows
                if isinstance(row["output_manifest"], dict)
            }

    def engineering_semantic_coverage(
        self, claimed: ClaimedJob, *, profile_version: str
    ) -> dict[str, int | bool]:
        """Return exact current-source coverage without accepting failed leaves.

        The bounded batch ledger is immutable history.  A successful durable job
        may therefore have useful accepted observations while one terminal leaf
        remains unresolved; that result is partial, never a complete stage.
        """
        with self._session(claimed) as session:
            row = (
                session.execute(
                    sa.text(
                        "WITH latest_elements AS (SELECT DISTINCT ON (source_locator_id) normalized_text "
                        "FROM workspace.native_layout_element_versions WHERE organization_id=:o AND "
                        "workspace_id=:w AND source_version_id=:source ORDER BY source_locator_id,version DESC), "
                        "expected AS (SELECT COALESCE(SUM(CEIL(length(normalized_text)::numeric/2400)),0)::bigint "
                        "AS fragment_count FROM latest_elements WHERE normalized_text<>''), "
                        "accepted AS (SELECT DISTINCT fragment->>'fragment_id' AS fragment_id FROM "
                        "workspace.engineering_extraction_batches batch CROSS JOIN LATERAL "
                        "jsonb_array_elements(CASE WHEN jsonb_typeof(batch.input_manifest)='array' "
                        "THEN batch.input_manifest ELSE COALESCE(batch.input_manifest->'fragments','[]'::jsonb) END) "
                        "AS fragment WHERE batch.organization_id=:o AND batch.workspace_id=:w AND "
                        "batch.source_version_id=:source AND batch.profile_version=:profile AND "
                        "batch.terminal_status='accepted'), failed AS (SELECT DISTINCT fragment->>'fragment_id' "
                        "AS fragment_id FROM workspace.engineering_extraction_batches batch CROSS JOIN LATERAL "
                        "jsonb_array_elements(CASE WHEN jsonb_typeof(batch.input_manifest)='array' "
                        "THEN batch.input_manifest ELSE COALESCE(batch.input_manifest->'fragments','[]'::jsonb) END) "
                        "AS fragment WHERE batch.organization_id=:o AND batch.workspace_id=:w AND "
                        "batch.source_version_id=:source AND batch.profile_version=:profile AND "
                        "batch.terminal_status='failed'), unresolved AS (SELECT COUNT(*)::bigint AS fragment_count "
                        "FROM failed LEFT JOIN accepted USING (fragment_id) WHERE accepted.fragment_id IS NULL) "
                        "SELECT expected.fragment_count AS expected_fragment_count,COUNT(accepted.fragment_id)::bigint "
                        "AS accepted_fragment_count,unresolved.fragment_count AS unresolved_failed_fragment_count "
                        "FROM expected CROSS JOIN unresolved LEFT JOIN accepted ON true GROUP BY expected.fragment_count,"
                        "unresolved.fragment_count"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "source": self._source_version_id(claimed),
                        "profile": profile_version,
                    },
                )
                .mappings()
                .one()
            )
        expected = int(row["expected_fragment_count"])
        accepted = int(row["accepted_fragment_count"])
        unresolved = int(row["unresolved_failed_fragment_count"])
        return {
            "expected_fragment_count": expected,
            "accepted_fragment_count": accepted,
            "unresolved_failed_fragment_count": unresolved,
            "complete": expected > 0 and accepted == expected and unresolved == 0,
        }

    def record_accepted_engineering_batch(
        self,
        claimed: ClaimedJob,
        *,
        profile_version: str,
        batch_ordinal: int,
        batch_digest: str,
        source_locator_ids: tuple[UUID, ...],
        input_manifest: dict[str, object],
        output_manifest: dict[str, object],
    ) -> None:
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.engineering_extraction_batches "
                    "(organization_id,workspace_id,source_version_id,profile_version,batch_ordinal,"
                    "batch_digest,source_locator_ids,input_manifest,output_manifest,output_digest,terminal_status) VALUES "
                    "(:o,:w,:source,:profile,:ordinal,:batch,:locators,CAST(:input_manifest AS jsonb),CAST(:manifest AS jsonb),"
                    ":output,'accepted') ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "source": self._source_version_id(claimed),
                    "profile": profile_version,
                    "ordinal": batch_ordinal,
                    "batch": batch_digest,
                    "locators": list(source_locator_ids),
                    "input_manifest": _json(input_manifest),
                    "manifest": _json(output_manifest),
                    "output": semantic_digest(output_manifest),
                },
            )

    def record_failed_engineering_batch(
        self,
        claimed: ClaimedJob,
        *,
        profile_version: str,
        batch_ordinal: int,
        batch_digest: str,
        source_locator_ids: tuple[UUID, ...],
        input_manifest: dict[str, object],
        failure_code: str,
        failure_diagnostics: dict[str, object],
    ) -> None:
        """Persist a sanitized failed model attempt without accepting its output."""
        output_manifest = {
            "contract": "engineering-extraction-batch-failure-v1",
            "typed_failure_code": failure_code,
            "diagnostics": failure_diagnostics,
        }
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.engineering_extraction_batches "
                    "(organization_id,workspace_id,source_version_id,profile_version,batch_ordinal,"
                    "batch_digest,source_locator_ids,input_manifest,output_manifest,output_digest,"
                    "terminal_status,typed_failure_code) VALUES "
                    "(:o,:w,:source,:profile,:ordinal,:batch,:locators,CAST(:input_manifest AS jsonb),"
                    "CAST(:manifest AS jsonb),:output,'failed',:failure) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "source": self._source_version_id(claimed),
                    "profile": profile_version,
                    "ordinal": batch_ordinal,
                    "batch": batch_digest,
                    "locators": list(source_locator_ids),
                    "input_manifest": _json(input_manifest),
                    "manifest": _json(output_manifest),
                    "output": semantic_digest(output_manifest),
                    "failure": failure_code,
                },
            )

    def record_engineering_batch_progress(
        self,
        claimed: ClaimedJob,
        *,
        completed_batches: int,
        total_batches: int,
    ) -> None:
        """Append a deduplicated, content-free progress event for a Qwen batch pass."""
        if total_batches < 1 or not 0 <= completed_batches <= total_batches:
            raise ValueError("engineering_batch_progress_invalid")
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "SELECT job_id FROM workspace.durable_jobs WHERE organization_id=:o "
                    "AND workspace_id=:w AND job_id=:job FOR UPDATE"
                ),
                {"o": claimed.organization_id, "w": claimed.workspace_id, "job": claimed.job_id},
            ).one()
            existing = session.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM workspace.job_progress_events WHERE "
                    "organization_id=:o AND workspace_id=:w AND job_id=:job AND "
                    "event_type='engineering.semantic_batch_progress' AND "
                    "progress_current=:current AND progress_total=:total)"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "job": claimed.job_id,
                    "current": completed_batches,
                    "total": total_batches,
                },
            )
            if existing:
                return
            sequence = int(
                session.scalar(
                    sa.text(
                        "SELECT COALESCE(max(event_sequence),0)+1 FROM workspace.job_progress_events "
                        "WHERE organization_id=:o AND workspace_id=:w AND job_id=:job"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "job": claimed.job_id,
                    },
                )
            )
            recorded_at = datetime.now(UTC)
            event_digest = semantic_digest(
                {
                    "job_id": claimed.job_id,
                    "sequence": sequence,
                    "event_type": "engineering.semantic_batch_progress",
                    "current": completed_batches,
                    "total": total_batches,
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.job_progress_events "
                    "(organization_id,workspace_id,job_id,event_sequence,event_type,progress_current,"
                    "progress_total,safe_message_code,terminal,recorded_at,retention_until,event_digest) "
                    "VALUES (:o,:w,:job,:sequence,'engineering.semantic_batch_progress',:current,:total,"
                    "'engineering_semantic_batch_accepted',false,:recorded,:retention,:digest)"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "job": claimed.job_id,
                    "sequence": sequence,
                    "current": completed_batches,
                    "total": total_batches,
                    "recorded": recorded_at,
                    "retention": recorded_at + timedelta(days=1),
                    "digest": event_digest,
                },
            )

    def persist_native_document(self, claimed: ClaimedJob, document: NativeDocument) -> None:
        inventory_id = deterministic_uuid(
            f"format-inventory:{self._source_version_id(claimed)}:{document.fingerprint}"
        )
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.document_format_inventories "
                    "(organization_id,workspace_id,inventory_id,document_id,document_version,"
                    "source_version_id,media_type,format_kind,parser_key,parser_version,page_count,"
                    "capability_gaps,inventory_digest) VALUES "
                    "(:o,:w,:inventory,:document,:version,:source,:media,:kind,:parser,:parser_version,"
                    ":pages,:gaps,:digest) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "inventory": inventory_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                    "source": self._source_version_id(claimed),
                    "media": document.media_type,
                    "kind": document.format_kind,
                    "parser": document.parser_key,
                    "parser_version": document.parser_version,
                    "pages": len(document.pages),
                    "gaps": list(document.capability_gaps),
                    "digest": document.fingerprint,
                },
            )
            for page in document.pages:
                health = page.health
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.document_page_health_versions "
                        "(organization_id,workspace_id,document_id,document_version,page_number,health_version,"
                        "page_health_id,primary_kind,signals,text_character_count,replacement_character_ratio,"
                        "image_count,rotation_degrees,width_points,height_points,ocr_route,profile_version,fingerprint) "
                        "VALUES (:o,:w,:document,:version,:page,1,:health,:kind,:signals,:characters,:replacement,"
                        ":images,:rotation,:width,:height,:route,:profile,:fingerprint) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "document": self._document_id(claimed),
                        "version": self._document_version(claimed),
                        "page": page.page_number,
                        "health": health.page_health_id,
                        "kind": health.primary_kind.value,
                        "signals": list(health.signals),
                        "characters": health.text_character_count,
                        "replacement": health.replacement_character_ratio,
                        "images": health.image_count,
                        "rotation": health.rotation_degrees,
                        "width": health.width_points,
                        "height": health.height_points,
                        "route": health.route.value,
                        "profile": health.profile_version,
                        "fingerprint": health.fingerprint,
                    },
                )
                self._persist_elements(session, claimed, page.elements, "native_layout")

    def persist_ocr_result(
        self,
        claimed: ClaimedJob,
        *,
        page_number: int,
        result: OcrAdapterResult,
    ) -> None:
        extraction_id = deterministic_uuid(
            f"ocr-extraction:{self._source_version_id(claimed)}:{page_number}:"
            f"{result.adapter_key}:{result.output_digest}"
        )
        with self._session(claimed) as session:
            session.execute(
                sa.text(
                    "INSERT INTO workspace.ocr_extraction_versions "
                    "(organization_id,workspace_id,ocr_extraction_id,version,document_id,document_version,"
                    "page_number,source_version_id,source_image_digest,adapter_key,adapter_version,"
                    "language_profile,output_digest,status) VALUES "
                    "(:o,:w,:extraction,1,:document,:version,:page,:source,:image,:adapter,:adapter_version,"
                    ":language,:output,'complete') ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "extraction": extraction_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                    "page": page_number,
                    "source": self._source_version_id(claimed),
                    "image": result.source_image_digest,
                    "adapter": result.adapter_key,
                    "adapter_version": result.adapter_version,
                    "language": result.language_profile,
                    "output": result.output_digest,
                },
            )
            self._persist_elements(session, claimed, result.elements, f"ocr:{result.adapter_key}")

    def load_elements(self, claimed: ClaimedJob) -> tuple[LayoutElement, ...]:
        with self._session(claimed) as session:
            rows = session.execute(
                sa.text(
                    "SELECT element_id,element_kind,raw_text,normalized_text,reading_order,region,cell_locator,"
                    "row_index,column_index,source_version_id,source_locator_id,page_number,evidence_digest "
                    "FROM workspace.native_layout_element_versions WHERE organization_id=:o AND workspace_id=:w "
                    "AND document_id=:document AND document_version=:version ORDER BY page_number,reading_order,element_id"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                },
            ).mappings()
        values: list[LayoutElement] = []
        for row in rows:
            region = tuple(float(value) for value in row["region"])
            locator = ExactLocator(
                UUID(str(row["source_version_id"])),
                UUID(str(row["source_locator_id"])),
                self._document_id(claimed),
                self._document_version(claimed),
                int(row["page_number"]),
                region,  # type: ignore[arg-type]
                str(row["evidence_digest"]),
                str(row["cell_locator"]) if row["cell_locator"] else None,
            )
            values.append(
                LayoutElement(
                    UUID(str(row["element_id"])),
                    str(row["element_kind"]),
                    str(row["raw_text"]),
                    str(row["normalized_text"]),
                    int(row["reading_order"]),
                    locator,
                    row_index=int(row["row_index"]) if row["row_index"] else None,
                    column_index=int(row["column_index"]) if row["column_index"] else None,
                )
            )
        return tuple(values)

    def load_ocr_routes(self, claimed: ClaimedJob) -> tuple[tuple[int, str], ...]:
        with self._session(claimed) as session:
            rows = session.execute(
                sa.text(
                    "SELECT DISTINCT ON (page_number) page_number,ocr_route FROM "
                    "workspace.document_page_health_versions WHERE organization_id=:o AND workspace_id=:w "
                    "AND document_id=:document AND document_version=:version "
                    "ORDER BY page_number,health_version DESC"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                },
            ).all()
        return tuple((int(row.page_number), str(row.ocr_route)) for row in rows)

    def load_completed_ocr_pages(self, claimed: ClaimedJob, *, adapter_key: str) -> frozenset[int]:
        """Return persisted successful pages for the active OCR adapter.

        A derived durable retry must continue a partially completed Qwen OCR
        attempt instead of sending the same source pages back to inference.
        Results from a different historical adapter deliberately do not satisfy
        the active Qwen route: their provenance remains preserved, but it is
        not silently promoted to the current model-based execution policy.
        """
        with self._session(claimed) as session:
            rows = session.scalars(
                sa.text(
                    "SELECT DISTINCT page_number FROM workspace.ocr_extraction_versions "
                    "WHERE organization_id=:o AND workspace_id=:w AND document_id=:document "
                    "AND document_version=:version AND source_version_id=:source "
                    "AND adapter_key=:adapter AND status='complete' ORDER BY page_number"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                    "source": self._source_version_id(claimed),
                    "adapter": adapter_key,
                },
            ).all()
        return frozenset(int(page_number) for page_number in rows)

    def persist_classification(
        self,
        claimed: ClaimedJob,
        candidates: tuple[RoleCandidate, ...],
        decisions: tuple[RoleDecision, ...],
    ) -> None:
        with self._session(claimed) as session:
            for candidate in candidates:
                candidate_digest = semantic_digest(candidate)
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.document_page_role_candidates "
                        "(organization_id,workspace_id,candidate_id,version,document_id,document_version,"
                        "scope,role,score,signal_codes,source_locator_ids,extraction_profile_version,"
                        "model_attempt_id,candidate_digest) VALUES "
                        "(:o,:w,:candidate,1,:document,:version,:scope,:role,:score,:signals,:locators,"
                        ":profile,:attempt,:digest) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "candidate": candidate.candidate_id,
                        "document": self._document_id(claimed),
                        "version": self._document_version(claimed),
                        "scope": candidate.scope,
                        "role": candidate.role.value,
                        "score": candidate.score,
                        "signals": list(candidate.signal_codes),
                        "locators": [item.source_locator_id for item in candidate.locators],
                        "profile": candidate.extraction_profile_version,
                        "attempt": candidate.model_attempt_id,
                        "digest": candidate_digest,
                    },
                )
            for decision in decisions:
                decision_digest = semantic_digest(decision)
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.document_role_decisions "
                        "(organization_id,workspace_id,decision_id,decision_version,document_id,document_version,"
                        "scope,selected_roles,candidate_ids,decision_code,validator_version,source_locator_ids,decision_digest) "
                        "VALUES (:o,:w,:decision,:decision_version,:document,:version,:scope,:roles,:candidates,"
                        ":code,:validator,:locators,:digest) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "decision": decision.decision_id,
                        "decision_version": decision.decision_version,
                        "document": self._document_id(claimed),
                        "version": self._document_version(claimed),
                        "scope": decision.scope,
                        "roles": [item.value for item in decision.selected_roles],
                        "candidates": list(decision.candidate_ids),
                        "code": decision.decision_code,
                        "validator": decision.validator_version,
                        "locators": [item.source_locator_id for item in decision.locators],
                        "digest": decision_digest,
                    },
                )

    def load_role_decisions(self, claimed: ClaimedJob) -> tuple[RoleDecision, ...]:
        elements = {
            item.locator.source_locator_id: item.locator for item in self.load_elements(claimed)
        }
        with self._session(claimed) as session:
            rows = session.execute(
                sa.text(
                    "SELECT decision_id,decision_version,scope,selected_roles,candidate_ids,decision_code,"
                    "validator_version,source_locator_ids FROM workspace.document_role_decisions "
                    "WHERE organization_id=:o AND workspace_id=:w AND document_id=:document "
                    "AND document_version=:version ORDER BY scope,decision_version DESC"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "document": self._document_id(claimed),
                    "version": self._document_version(claimed),
                },
            ).mappings()
        return tuple(
            RoleDecision(
                UUID(str(row["decision_id"])),
                int(row["decision_version"]),
                str(row["scope"]),
                tuple(DocumentRole(str(item)) for item in row["selected_roles"]),
                tuple(UUID(str(item)) for item in row["candidate_ids"]),
                str(row["decision_code"]),
                str(row["validator_version"]),
                tuple(
                    elements[UUID(str(item))]
                    for item in row["source_locator_ids"]
                    if UUID(str(item)) in elements
                ),
            )
            for row in rows
        )

    def persist_structured(self, claimed: ClaimedJob, bundle: StructuredCandidates) -> None:
        with self._session(claimed) as session:
            for field_candidate in bundle.project_fields:
                self._insert_project_field(session, claimed, field_candidate)
            for structure_candidate in bundle.structures:
                self._insert_structure(session, claimed, structure_candidate)
            for relationship_candidate in bundle.structure_relationships:
                self._insert_structure_relationship(session, claimed, relationship_candidate)
            for work_candidate in bundle.works:
                self._insert_work(session, claimed, work_candidate)
            for quantity_candidate in bundle.quantities:
                self._insert_quantity(session, claimed, quantity_candidate)
            for material_candidate in bundle.materials:
                self._insert_material(session, claimed, material_candidate)
            for estimate_candidate in bundle.estimates:
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.estimate_position_candidates "
                        "(organization_id,workspace_id,candidate_id,version,raw_position,normalized_description,"
                        "raw_quantity,parsed_quantity,raw_unit,source_version_id,source_locator_id,candidate_digest) "
                        "VALUES (:o,:w,:candidate,1,:position,:description,:raw_quantity,:parsed,:unit,:source,"
                        ":locator,:digest) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "candidate": estimate_candidate.candidate_id,
                        "position": estimate_candidate.raw_position,
                        "description": estimate_candidate.normalized_description,
                        "raw_quantity": estimate_candidate.raw_quantity,
                        "parsed": estimate_candidate.parsed_quantity,
                        "unit": estimate_candidate.raw_unit,
                        "source": estimate_candidate.locator.source_version_id,
                        "locator": estimate_candidate.locator.source_locator_id,
                        "digest": semantic_digest(estimate_candidate),
                    },
                )
            for defect in bundle.defects:
                self._insert_defect(session, claimed, defect)

    def persist_structure_identity_candidates(
        self, claimed: ClaimedJob, values: tuple[StructureIdentityCandidate, ...]
    ) -> None:
        """Persist only validated, multi-observation Qwen identity candidates.

        Node membership is checked inside the scoped transaction.  The table uses
        arrays to preserve immutable observation membership; this guard prevents an
        adapter response from naming an unrelated workspace's node.
        """
        with self._session(claimed) as session:
            for value in values:
                member_ids = list(value.member_structure_node_ids)
                locator_ids = list(value.source_locator_ids)
                membership = (
                    session.execute(
                        sa.text(
                            "SELECT count(DISTINCT structure_node_id) AS member_count, "
                            "count(DISTINCT source_locator_id) AS member_locator_count, "
                            "count(DISTINCT source_locator_id) FILTER (WHERE source_locator_id=ANY(:locators)) "
                            "AS matched_locator_count FROM workspace.project_structure_node_versions "
                            "WHERE organization_id=:o AND workspace_id=:w "
                            "AND structure_node_id=ANY(:members)"
                        ),
                        {
                            "o": claimed.organization_id,
                            "w": claimed.workspace_id,
                            "members": member_ids,
                            "locators": locator_ids,
                        },
                    )
                    .mappings()
                    .one()
                )
                if int(membership["member_count"]) != len(member_ids):
                    raise UnderstandingPersistenceError("structure_identity_member_unavailable")
                if int(membership["member_locator_count"]) != len(set(locator_ids)) or int(
                    membership["matched_locator_count"]
                ) != len(set(locator_ids)):
                    raise UnderstandingPersistenceError("structure_identity_locator_unavailable")
                session.execute(
                    sa.text(
                        "INSERT INTO workspace.project_structure_identity_candidates "
                        "(organization_id,workspace_id,identity_candidate_id,version,identity_kind,"
                        "canonical_label,member_structure_node_ids,source_locator_ids,confidence,status,"
                        "reconciliation_profile_version,candidate_digest) VALUES "
                        "(:o,:w,:candidate,1,:kind,:label,:members,:locators,:confidence,:status,:profile,:digest) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "candidate": value.identity_candidate_id,
                        "kind": value.identity_kind,
                        "label": value.canonical_label,
                        "members": member_ids,
                        "locators": locator_ids,
                        "confidence": value.confidence,
                        "status": value.status.value,
                        "profile": value.reconciliation_profile_version,
                        "digest": semantic_digest(value),
                    },
                )

    def load_structure_identity_observation_groups(
        self, claimed: ClaimedJob, *, profile_version: str
    ) -> tuple[tuple[dict[str, object], ...], ...]:
        """Return bounded cross-source comparison groups without joining them."""
        with self._session(claimed) as session:
            rows = (
                session.execute(
                    sa.text(
                        "SELECT n.structure_node_id,n.node_kind,n.raw_name,n.normalized_name,"
                        "n.source_locator_id,locator.source_version_id,"
                        "COALESCE(locator.locator_value->>'page','') AS page,"
                        "document.safe_display_name,COALESCE(evidence.normalized_text,'') AS evidence_excerpt "
                        "FROM workspace.project_structure_node_versions n "
                        "JOIN workspace.source_locators locator ON locator.organization_id=n.organization_id "
                        "AND locator.workspace_id=n.workspace_id AND locator.source_locator_id=n.source_locator_id "
                        "JOIN workspace.document_versions document ON document.organization_id=locator.organization_id "
                        "AND document.workspace_id=locator.workspace_id AND document.source_version_id=locator.source_version_id "
                        "LEFT JOIN LATERAL (SELECT left(element.normalized_text,700) AS normalized_text "
                        "FROM workspace.native_layout_element_versions element WHERE element.organization_id=n.organization_id "
                        "AND element.workspace_id=n.workspace_id AND element.source_locator_id=n.source_locator_id "
                        "ORDER BY element.version DESC LIMIT 1) evidence ON true "
                        "WHERE n.organization_id=:o AND n.workspace_id=:w AND n.extraction_profile_version=:profile "
                        "ORDER BY n.node_kind,n.normalized_name,locator.source_version_id,n.structure_node_id"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "profile": profile_version,
                    },
                )
                .mappings()
                .all()
            )
        grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in rows:
            value = dict(row)
            grouped.setdefault(
                (
                    str(value["node_kind"]),
                    _identity_observation_group_key(str(value["normalized_name"])),
                ),
                [],
            ).append(value)
        result: list[tuple[dict[str, object], ...]] = []
        for values in grouped.values():
            if len({str(item["source_version_id"]) for item in values}) < 2:
                continue
            for offset in range(0, len(values), 48):
                group = tuple(values[offset : offset + 48])
                if len({str(item["source_version_id"]) for item in group}) >= 2:
                    result.append(group)
        return tuple(result)

    def workspace_engineering_semantic_coverage(
        self, claimed: ClaimedJob, *, profile_version: str
    ) -> dict[str, int | bool]:
        """Require every active source to have a complete matching semantic receipt."""
        with self._session(claimed) as session:
            row = (
                session.execute(
                    sa.text(
                        "WITH active_sources AS (SELECT DISTINCT ON (v.document_id) v.source_version_id "
                        "FROM workspace.document_versions v JOIN workspace.document_version_activation_decisions a "
                        "ON a.organization_id=v.organization_id AND a.workspace_id=v.workspace_id "
                        "AND a.document_id=v.document_id AND a.selected_document_version=v.version "
                        "WHERE v.organization_id=:o AND v.workspace_id=:w AND NOT EXISTS (SELECT 1 FROM "
                        "workspace.document_version_activation_decisions newer WHERE newer.organization_id=a.organization_id "
                        "AND newer.workspace_id=a.workspace_id AND newer.document_id=a.document_id "
                        "AND newer.decision_version>a.decision_version)), completed AS (SELECT DISTINCT "
                        "result.source_version_id FROM workspace.project_understanding_stage_results result "
                        "JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                        "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                        "WHERE result.organization_id=:o AND result.workspace_id=:w AND "
                        "result.stage_kind='PROJECT_DEFINITION_EXTRACTION' AND result.terminal_status='complete' "
                        "AND COALESCE(job.provenance->>'engineering_semantic_profile',result.profile_version)=:profile) "
                        "SELECT count(*)::int AS source_count,count(completed.source_version_id)::int AS complete_source_count "
                        "FROM active_sources LEFT JOIN completed USING(source_version_id)"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "profile": profile_version,
                    },
                )
                .mappings()
                .one()
            )
        total = int(row["source_count"])
        completed = int(row["complete_source_count"])
        return {
            "source_count": total,
            "complete_source_count": completed,
            "complete": total > 0 and total == completed,
        }

    def assemble_workspace(self, claimed: ClaimedJob) -> dict[str, Any]:
        with self._session(claimed) as session:
            source_ids = self._active_source_ids(session, claimed)
            if not source_ids:
                raise UnderstandingPersistenceError("project_sources_unavailable")
            fields = self._current_rows(session, claimed, "project_field_candidates", source_ids)
            works = self._current_rows(session, claimed, "work_type_candidates", source_ids)
            quantities = self._work_child_rows(session, claimed, "quantity_candidates", source_ids)
            materials = self._work_child_rows(session, claimed, "material_candidates", source_ids)
            structures = self._current_structure_rows(session, claimed, source_ids)
            structure_relationships = self._current_structure_relationship_rows(
                session, claimed, source_ids
            )
            defects = self._current_defects(session, claimed, source_ids)
            review_digests = session.scalars(
                sa.text(
                    "SELECT decision_digest FROM workspace.project_candidate_review_decisions WHERE "
                    "organization_id=:o AND workspace_id=:w ORDER BY review_decision_id,decision_version"
                ),
                {"o": claimed.organization_id, "w": claimed.workspace_id},
            ).all()
            corpus_digest = semantic_digest(
                {
                    "source_version_ids": [str(item) for item in source_ids],
                    "review_decisions": list(review_digests),
                    "candidate_inputs": self._materialization_input_digest(
                        fields=fields,
                        works=works,
                        quantities=quantities,
                        materials=materials,
                        structures=structures,
                        relationships=structure_relationships,
                        defects=defects,
                    ),
                }
            )
            run_id = deterministic_uuid(
                f"project-understanding-run:{claimed.organization_id}:{claimed.workspace_id}:"
                f"{corpus_digest}:{UNDERSTANDING_PROFILE_VERSION}"
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_understanding_runs "
                    "(organization_id,workspace_id,run_id,version,corpus_manifest_digest,profile_version,"
                    "state,source_version_ids,gaps) VALUES "
                    "(:o,:w,:run,1,:corpus,:profile,'assembling',:sources,:gaps) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "run": run_id,
                    "corpus": corpus_digest,
                    "profile": UNDERSTANDING_PROFILE_VERSION,
                    "sources": source_ids,
                    "gaps": ["VERIFIED_NTD_UNAVAILABLE", "ACTIVE_RULE_VERSION_UNAVAILABLE"],
                },
            )
            project_id, project_fingerprint, field_gaps, project_dimensions = (
                self._assemble_project_definition(
                    session, claimed, source_ids, fields, corpus_digest
                )
            )
            package_rows = self._assemble_work_packages(
                session,
                claimed,
                project_id,
                works,
                quantities,
                materials,
            )
            normative_profile = self._assemble_pd_rd_profile(
                session, claimed, project_id, project_dimensions
            )
            matrix_id, matrix_fingerprint = self._assemble_matrix(
                session, claimed, project_id, package_rows, corpus_digest, normative_profile
            )
            page_count = int(
                session.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.document_page_health_versions WHERE "
                        "organization_id=:o AND workspace_id=:w AND health_version=1"
                    ),
                    {"o": claimed.organization_id, "w": claimed.workspace_id},
                )
                or 0
            )
            unresolved_work_count = sum(
                1 for item in works if item["canonical_mapping_status"] != "resolved"
            )
            package_gaps = {
                str(gap) for package in package_rows for gap in package["uncertainties"]
            }
            gaps = sorted(
                {
                    *[str(item["code"]) for item in normative_profile["gaps"]],
                    *package_gaps,
                    *field_gaps,
                    *(
                        {"STRUCTURE_CANDIDATE_RECONCILIATION_PENDING"}
                        if structures or structure_relationships
                        else set()
                    ),
                }
            )
            terminal_status = (
                "complete" if not gaps and not defects and unresolved_work_count == 0 else "partial"
            )
            structural = semantic_digest(
                {
                    "run": run_id,
                    "sources": [str(item) for item in source_ids],
                    "project": project_fingerprint,
                    "matrix": matrix_fingerprint,
                    "packages": [item["fingerprint"] for item in package_rows],
                    "structure_candidates": [
                        (str(item["structure_node_id"]), int(item["version"]))
                        for item in structures
                    ],
                    "structure_relationship_candidates": [
                        (str(item["relationship_candidate_id"]), int(item["version"]))
                        for item in structure_relationships
                    ],
                    "defects": [str(item["defect_id"]) for item in defects],
                    "gaps": gaps,
                }
            )
            reconciliation_id = deterministic_uuid(
                f"project-understanding-reconciliation:{run_id}:{structural}"
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_understanding_reconciliations "
                    "(organization_id,workspace_id,reconciliation_id,version,run_id,run_version,"
                    "project_definition_id,project_definition_version,matrix_id,matrix_version,source_count,"
                    "page_count,accepted_candidate_count,unresolved_candidate_count,open_defect_count,gaps,"
                    "structural_fingerprint,terminal_status) VALUES "
                    "(:o,:w,:reconciliation,1,:run,1,:project,1,:matrix,1,:sources,:pages,:accepted,"
                    ":unresolved,:defects,:gaps,:fingerprint,:status) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "reconciliation": reconciliation_id,
                    "run": run_id,
                    "project": project_id,
                    "matrix": matrix_id,
                    "sources": len(source_ids),
                    "pages": page_count,
                    "accepted": (
                        len(fields)
                        + len(works)
                        + len(quantities)
                        + len(materials)
                        + len(structures)
                        + len(structure_relationships)
                    ),
                    "unresolved": unresolved_work_count,
                    "defects": len(defects),
                    "gaps": gaps,
                    "fingerprint": structural,
                    "status": terminal_status,
                },
            )
            self._rebuild_projection_in_session(
                session,
                organization_id=claimed.organization_id,
                workspace_id=claimed.workspace_id,
                run_id=run_id,
                run_version=1,
                project_definition_id=project_id,
                matrix_id=matrix_id,
            )
        return {
            "run_id": str(run_id),
            "run_version": 1,
            "project_definition_id": str(project_id),
            "matrix_id": str(matrix_id),
            "work_package_count": len(package_rows),
            "structure_candidate_count": len(structures),
            "structure_relationship_candidate_count": len(structure_relationships),
            "defect_count": len(defects),
            "gaps": gaps,
            "structural_fingerprint": structural,
            "terminal_status": terminal_status,
        }

    def rebuild_project_understanding_projection(
        self, *, organization_id: UUID, workspace_id: UUID
    ) -> str:
        with Session(self._engine) as session, session.begin():
            _set_scope(session, organization_id, workspace_id)
            selected = (
                session.execute(
                    sa.text(
                        "SELECT run_id,run_version,project_definition_id,matrix_id FROM "
                        "workspace.project_understanding_reconciliations WHERE organization_id=:o "
                        "AND workspace_id=:w ORDER BY recorded_at DESC,reconciliation_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            if selected is None:
                raise UnderstandingPersistenceError(
                    "project_understanding_reconciliation_unavailable"
                )
            fingerprints = self._rebuild_projection_in_session(
                session,
                organization_id=organization_id,
                workspace_id=workspace_id,
                run_id=UUID(str(selected["run_id"])),
                run_version=int(selected["run_version"]),
                project_definition_id=UUID(str(selected["project_definition_id"])),
                matrix_id=UUID(str(selected["matrix_id"])),
            )
        return semantic_digest({"entries": sorted(fingerprints)})

    @staticmethod
    def _rebuild_projection_in_session(
        session: Session,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        run_id: UUID,
        run_version: int,
        project_definition_id: UUID,
        matrix_id: UUID,
    ) -> tuple[str, ...]:
        session.execute(
            sa.text(
                "DELETE FROM projection.project_understanding_entries WHERE organization_id=:o "
                "AND workspace_id=:w AND run_id=:run AND run_version=:version"
            ),
            {"o": organization_id, "w": workspace_id, "run": run_id, "version": run_version},
        )
        project = (
            session.execute(
                sa.text(
                    "SELECT definition,fingerprint FROM workspace.project_definition_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND project_definition_id=:project "
                    "AND version=1"
                ),
                {"o": organization_id, "w": workspace_id, "project": project_definition_id},
            )
            .mappings()
            .one()
        )
        packages = session.execute(
            sa.text(
                "SELECT work_package_id,package,fingerprint FROM "
                "workspace.construction_work_package_versions WHERE organization_id=:o AND "
                "workspace_id=:w AND project_definition_id=:project ORDER BY work_package_id"
            ),
            {"o": organization_id, "w": workspace_id, "project": project_definition_id},
        ).mappings()
        matrix = (
            session.execute(
                sa.text(
                    "SELECT matrix,fingerprint FROM workspace.work_requirement_matrix_versions WHERE "
                    "organization_id=:o AND workspace_id=:w AND matrix_id=:matrix AND version=1"
                ),
                {"o": organization_id, "w": workspace_id, "matrix": matrix_id},
            )
            .mappings()
            .one()
        )
        entries: list[tuple[str, str, tuple[UUID, ...], dict[str, Any]]] = []
        definition = dict(project["definition"])
        project_locators = tuple(
            sorted(
                {
                    UUID(str(value["source_locator_id"]))
                    for value in dict(definition.get("fields", {})).values()
                    if isinstance(value, dict) and value.get("source_locator_id")
                },
                key=str,
            )
        )
        entries.append(
            (
                "project_definition",
                str(project_definition_id),
                project_locators,
                {"definition": definition, "canonical_fingerprint": str(project["fingerprint"])},
            )
        )
        for package_row in packages:
            package = dict(package_row["package"])
            locators = tuple(UUID(str(value)) for value in package.get("source_locator_ids", []))
            entries.append(
                (
                    "work_package",
                    str(package_row["work_package_id"]),
                    locators,
                    {"package": package, "canonical_fingerprint": str(package_row["fingerprint"])},
                )
            )
        entries.append(
            (
                "requirement_matrix",
                str(matrix_id),
                (),
                {
                    "matrix": dict(matrix["matrix"]),
                    "canonical_fingerprint": str(matrix["fingerprint"]),
                },
            )
        )
        fingerprints: list[str] = []
        for kind, identity, locators, entry in entries:
            fingerprint = semantic_digest(
                {
                    "run_id": run_id,
                    "run_version": run_version,
                    "entry_kind": kind,
                    "entry_identity": identity,
                    "source_locator_ids": [str(value) for value in locators],
                    "entry": entry,
                    "profile": "project-understanding-projection-v0.1",
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO projection.project_understanding_entries "
                    "(organization_id,workspace_id,run_id,run_version,entry_kind,entry_identity,"
                    "source_locator_ids,entry,projection_profile_version,entry_fingerprint) VALUES "
                    "(:o,:w,:run,:version,:kind,:identity,:locators,CAST(:entry AS jsonb),"
                    "'project-understanding-projection-v0.1',:fingerprint)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "run": run_id,
                    "version": run_version,
                    "kind": kind,
                    "identity": identity,
                    "locators": list(locators),
                    "entry": _json(entry),
                    "fingerprint": fingerprint,
                },
            )
            fingerprints.append(fingerprint)
        return tuple(fingerprints)

    def snapshot(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> ProjectUnderstandingSnapshot:
        with Session(self._engine) as session, session.begin():
            organization_id = session.scalar(
                sa.text("SELECT application.resolve_workspace_scope(:owner,:workspace)"),
                {"owner": owner_identity_id, "workspace": workspace_id},
            )
            if organization_id is None:
                raise UnderstandingPersistenceError("workspace_not_found")
            _set_scope(session, UUID(str(organization_id)), workspace_id)
            reconciliation = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.project_understanding_reconciliations WHERE "
                        "organization_id=:o AND workspace_id=:w ORDER BY recorded_at DESC,reconciliation_id DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            health = (
                session.execute(
                    sa.text(
                        "SELECT primary_kind,ocr_route,count(*) AS count FROM workspace.document_page_health_versions "
                        "WHERE organization_id=:o AND workspace_id=:w GROUP BY primary_kind,ocr_route"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .all()
            )
            roles = (
                session.execute(
                    sa.text(
                        "SELECT d.document_id,d.document_version,d.scope,d.selected_roles,d.source_locator_ids "
                        "FROM workspace.document_role_decisions d WHERE d.organization_id=:o AND d.workspace_id=:w "
                        "ORDER BY d.document_id,d.scope,d.decision_version"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .all()
            )
            fields = self._select_json_rows(
                session, "project_field_candidates", organization_id, workspace_id
            )
            structures = (
                session.execute(
                    sa.text(
                        "SELECT structure_node_id,version,node_kind,raw_name,normalized_name,parent_node_id,"
                        "source_locator_id,status,fingerprint FROM workspace.project_structure_node_versions "
                        "WHERE organization_id=:o AND workspace_id=:w ORDER BY recorded_at,structure_node_id"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .all()
            )
            works = self._select_json_rows(
                session, "work_type_candidates", organization_id, workspace_id
            )
            quantities = self._select_json_rows(
                session, "quantity_candidates", organization_id, workspace_id
            )
            materials = self._select_json_rows(
                session, "material_candidates", organization_id, workspace_id
            )
            packages = (
                session.execute(
                    sa.text(
                        "SELECT work_package_id,version,package,fingerprint FROM workspace.construction_work_package_versions "
                        "WHERE organization_id=:o AND workspace_id=:w ORDER BY created_at,work_package_id"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .all()
            )
            project = (
                session.execute(
                    sa.text(
                        "SELECT project_definition_id,version,definition,fingerprint FROM workspace.project_definition_versions "
                        "WHERE organization_id=:o AND workspace_id=:w ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            matrix = (
                session.execute(
                    sa.text(
                        "SELECT matrix_id,version,matrix,fingerprint FROM workspace.work_requirement_matrix_versions "
                        "WHERE organization_id=:o AND workspace_id=:w ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                .mappings()
                .one_or_none()
            )
            defects = self._select_json_rows(
                session, "project_reconciliation_defects", organization_id, workspace_id
            )
            documents = int(
                session.scalar(
                    sa.text(
                        "SELECT count(*) FROM workspace.document_records WHERE organization_id=:o AND workspace_id=:w"
                    ),
                    {"o": organization_id, "w": workspace_id},
                )
                or 0
            )
        health_counts: dict[str, int] = {}
        route_counts: dict[str, int] = {}
        for row in health:
            health_counts[str(row["primary_kind"])] = health_counts.get(
                str(row["primary_kind"]), 0
            ) + int(row["count"])
            route_counts[str(row["ocr_route"])] = route_counts.get(str(row["ocr_route"]), 0) + int(
                row["count"]
            )
        gaps = tuple(str(item) for item in (reconciliation["gaps"] if reconciliation else []))
        return ProjectUnderstandingSnapshot(
            UUID(str(reconciliation["run_id"])) if reconciliation else None,
            int(reconciliation["run_version"]) if reconciliation else None,
            str(reconciliation["terminal_status"]) if reconciliation else "no_result",
            documents,
            sum(health_counts.values()),
            dict(sorted(health_counts.items())),
            dict(sorted(route_counts.items())),
            tuple(_plain(dict(row)) for row in roles),
            _plain(dict(project)) if project else None,
            tuple(fields),
            tuple(_plain(dict(row)) for row in structures),
            tuple(works),
            tuple(quantities),
            tuple(materials),
            tuple(_plain(dict(row)) for row in packages),
            _plain(dict(matrix)) if matrix else None,
            tuple(defects),
            gaps,
            str(reconciliation["structural_fingerprint"]) if reconciliation else None,
        )

    def _persist_elements(
        self,
        session: Session,
        claimed: ClaimedJob,
        elements: tuple[LayoutElement, ...],
        extraction_method: str,
    ) -> None:
        for element in elements:
            locator = element.locator
            locator_value = {
                "page": locator.page_number,
                "region": locator.region,
                "coordinate_space": "normalized-top-left",
                "cell": locator.cell,
            }
            session.execute(
                sa.text(
                    "INSERT INTO workspace.source_locators "
                    "(organization_id,workspace_id,source_locator_id,source_version_id,locator_kind,"
                    "locator_key,locator_value,fragment_digest) VALUES "
                    "(:o,:w,:locator,:source,:kind,:key,CAST(:value AS jsonb),:fragment) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "locator": locator.source_locator_id,
                    "source": locator.source_version_id,
                    "kind": "document_page_region"
                    if locator.cell is None
                    else "document_table_cell",
                    "key": f"understanding:{extraction_method}:{locator.source_locator_id}",
                    "value": _json(locator_value),
                    "fragment": locator.evidence_digest,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.native_layout_element_versions "
                    "(organization_id,workspace_id,element_id,version,document_id,document_version,"
                    "source_version_id,source_locator_id,page_number,element_kind,raw_text,normalized_text,"
                    "reading_order,region,cell_locator,row_index,column_index,evidence_digest,extraction_method,"
                    "profile_version,semantic_digest) VALUES "
                    "(:o,:w,:element,1,:document,:version,:source,:locator,:page,:kind,:raw,:normalized,"
                    ":ordering,CAST(:region AS jsonb),:cell,:row,:column,:evidence,:method,"
                    "'native-layout-v0.1',:digest) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "element": element.element_id,
                    "document": locator.document_id,
                    "version": locator.document_version,
                    "source": locator.source_version_id,
                    "locator": locator.source_locator_id,
                    "page": locator.page_number,
                    "kind": element.kind,
                    "raw": element.raw_text,
                    "normalized": element.normalized_text,
                    "ordering": element.reading_order,
                    "region": _json(locator.region),
                    "cell": locator.cell,
                    "row": element.row_index,
                    "column": element.column_index,
                    "evidence": locator.evidence_digest,
                    "method": extraction_method,
                    "digest": semantic_digest(element),
                },
            )

    def _insert_project_field(
        self, session: Session, claimed: ClaimedJob, value: ProjectFieldCandidate
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.project_field_candidates "
                "(organization_id,workspace_id,candidate_id,version,field_key,raw_value,normalized_value,"
                "value_type,source_version_id,source_locator_id,extraction_method,confidence,uncertainty_codes,"
                "conflicts,status,extraction_profile_version,candidate_digest) VALUES "
                "(:o,:w,:candidate,1,:key,:raw,CAST(:normalized AS jsonb),:type,:source,:locator,:method,1,"
                ":uncertainty,'{}',:status,:profile,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": value.candidate_id,
                "key": value.field_key,
                "raw": value.raw_value,
                "normalized": _json(value.normalized_value),
                "type": value.value_type,
                "source": value.locator.source_version_id,
                "locator": value.locator.source_locator_id,
                "method": value.extraction_method,
                "uncertainty": list(value.uncertainty_codes),
                "status": value.status.value,
                "profile": value.extraction_profile_version,
                "digest": semantic_digest(value),
            },
        )

    @staticmethod
    def _insert_structure(
        session: Session, claimed: ClaimedJob, value: StructureNodeCandidate
    ) -> None:
        fingerprint = semantic_digest(value)
        session.execute(
            sa.text(
                "INSERT INTO workspace.project_structure_node_versions "
                "(organization_id,workspace_id,structure_node_id,version,node_kind,raw_name,"
                "normalized_name,parent_node_id,source_locator_id,status,extraction_profile_version,fingerprint) VALUES "
                "(:o,:w,:node,1,:kind,:raw,:normalized,NULL,:locator,:status,:profile,:fingerprint) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "node": value.structure_node_id,
                "kind": value.node_kind,
                "raw": value.raw_name,
                "normalized": value.normalized_name,
                "locator": value.locator.source_locator_id,
                "status": value.status.value,
                "profile": value.extraction_profile_version,
                "fingerprint": fingerprint,
            },
        )

    @staticmethod
    def _insert_structure_relationship(
        session: Session, claimed: ClaimedJob, value: StructureRelationshipCandidate
    ) -> None:
        """Persist unresolved relationship endpoints without name-based node joins."""
        session.execute(
            sa.text(
                "INSERT INTO workspace.project_structure_relationship_candidates "
                "(organization_id,workspace_id,relationship_candidate_id,version,relationship_kind,"
                "subject_raw_name,subject_normalized_name,object_raw_name,object_normalized_name,"
                "source_version_id,source_locator_id,status,extraction_profile_version,candidate_digest) VALUES "
                "(:o,:w,:candidate,1,:kind,:subject_raw,:subject_normalized,:object_raw,"
                ":object_normalized,:source,:locator,:status,:profile,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": value.relationship_candidate_id,
                "kind": value.relationship_kind,
                "subject_raw": value.subject_raw_name,
                "subject_normalized": value.subject_normalized_name,
                "object_raw": value.object_raw_name,
                "object_normalized": value.object_normalized_name,
                "source": value.locator.source_version_id,
                "locator": value.locator.source_locator_id,
                "status": value.status.value,
                "profile": value.extraction_profile_version,
                "digest": semantic_digest(value),
            },
        )

    def _insert_work(self, session: Session, claimed: ClaimedJob, value: WorkTypeCandidate) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.work_type_candidates "
                "(organization_id,workspace_id,candidate_id,version,raw_name,normalized_name,scope_key,"
                "source_role,source_version_id,source_locator_id,canonical_mapping_status,canonical_work_type_id,"
                "extraction_profile_version,candidate_digest) VALUES "
                "(:o,:w,:candidate,1,:raw,:normalized,:scope,:role,:source,:locator,:mapping,:canonical,"
                ":profile,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": value.candidate_id,
                "raw": value.raw_name,
                "normalized": value.normalized_name,
                "scope": value.scope_key,
                "role": value.source_role.value,
                "source": value.locator.source_version_id,
                "locator": value.locator.source_locator_id,
                "mapping": value.canonical_mapping_status.value,
                "canonical": value.canonical_work_type_id,
                "profile": value.extraction_profile_version,
                "digest": semantic_digest(value),
            },
        )

    def _insert_quantity(
        self, session: Session, claimed: ClaimedJob, value: QuantityCandidate
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.quantity_candidates "
                "(organization_id,workspace_id,candidate_id,version,work_candidate_id,work_candidate_version,"
                "raw_value,parsed_value,raw_unit,normalized_value,normalized_unit,conversion_rule_version,"
                "scope_key,source_locator_id,status,candidate_digest) VALUES "
                "(:o,:w,:candidate,1,:work,1,:raw,:parsed,:raw_unit,:normalized,:unit,:conversion,:scope,"
                ":locator,:status,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": value.candidate_id,
                "work": value.work_candidate_id,
                "raw": value.raw_value,
                "parsed": value.parsed_value,
                "raw_unit": value.raw_unit,
                "normalized": value.normalized_value,
                "unit": value.normalized_unit,
                "conversion": value.conversion_rule_version,
                "scope": value.scope_key,
                "locator": value.locator.source_locator_id,
                "status": value.status.value,
                "digest": semantic_digest(value),
            },
        )

    def _insert_material(
        self, session: Session, claimed: ClaimedJob, value: MaterialCandidate
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.material_candidates "
                "(organization_id,workspace_id,candidate_id,version,work_candidate_id,work_candidate_version,"
                "raw_name,normalized_name,raw_quantity,parsed_quantity,raw_unit,normalized_unit,source_locator_id,"
                "status,candidate_digest) VALUES "
                "(:o,:w,:candidate,1,:work,1,:raw,:normalized,:raw_quantity,:parsed,:raw_unit,:unit,:locator,"
                ":status,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "candidate": value.candidate_id,
                "work": value.work_candidate_id,
                "raw": value.raw_name,
                "normalized": value.normalized_name,
                "raw_quantity": value.raw_quantity,
                "parsed": value.parsed_quantity,
                "raw_unit": value.raw_unit,
                "unit": value.normalized_unit,
                "locator": value.locator.source_locator_id,
                "status": value.status.value,
                "digest": semantic_digest(value),
            },
        )

    def _insert_defect(
        self, session: Session, claimed: ClaimedJob, value: ReconciliationDefect
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO workspace.project_reconciliation_defects "
                "(organization_id,workspace_id,defect_id,version,defect_kind,subject_identity,related_identity,"
                "source_locator_ids,parameters,blocking,status,extraction_profile_version,defect_digest) VALUES "
                "(:o,:w,:defect,1,:kind,:subject,:related,:locators,CAST(:parameters AS jsonb),:blocking,'open',"
                ":profile,:digest) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "defect": value.defect_id,
                "kind": value.kind.value,
                "subject": value.subject_identity,
                "related": value.related_identity,
                "locators": [item.source_locator_id for item in value.evidence_locators],
                "parameters": _json(value.parameters),
                "blocking": value.blocking,
                "profile": value.extraction_profile_version,
                "digest": semantic_digest(value),
            },
        )

    @staticmethod
    def _active_source_ids(session: Session, claimed: ClaimedJob) -> list[UUID]:
        rows = session.scalars(
            sa.text(
                "SELECT v.source_version_id FROM workspace.document_versions v JOIN "
                "workspace.document_version_activation_decisions a ON a.organization_id=v.organization_id "
                "AND a.workspace_id=v.workspace_id AND a.document_id=v.document_id "
                "AND a.selected_document_version=v.version WHERE v.organization_id=:o AND v.workspace_id=:w "
                "AND NOT EXISTS (SELECT 1 FROM workspace.document_version_activation_decisions newer WHERE "
                "newer.organization_id=a.organization_id AND newer.workspace_id=a.workspace_id "
                "AND newer.document_id=a.document_id AND newer.decision_version>a.decision_version) "
                "ORDER BY v.source_version_id"
            ),
            {"o": claimed.organization_id, "w": claimed.workspace_id},
        ).all()
        return [UUID(str(value)) for value in rows]

    @staticmethod
    def _current_rows(
        session: Session, claimed: ClaimedJob, table: str, source_ids: list[UUID]
    ) -> list[dict[str, Any]]:
        if table not in {"project_field_candidates", "work_type_candidates"}:
            raise ValueError("invalid current-row relation")
        default_profile = (
            PROJECT_EXTRACTION_PROFILE_VERSION
            if table == "project_field_candidates"
            else WORK_EXTRACTION_PROFILE_VERSION
        )
        rows = (
            session.execute(
                sa.text(
                    "WITH selected_profiles AS (SELECT DISTINCT ON (result.source_version_id) "
                    "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                    "result.profile_version) AS semantic_profile FROM workspace.project_understanding_stage_results "
                    "result JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                    "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                    "WHERE result.organization_id=:o AND result.workspace_id=:w "
                    "AND result.source_version_id=ANY(:sources) "
                    "AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                    "AND result.terminal_status IN ('complete','partial') ORDER BY result.source_version_id,"
                    "result.recorded_at DESC,result.stage_result_id DESC) "
                    f"SELECT candidate.* FROM workspace.{table} candidate JOIN selected_profiles selected "
                    "ON selected.source_version_id=candidate.source_version_id WHERE "
                    "candidate.organization_id=:o AND candidate.workspace_id=:w AND "
                    "candidate.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                    "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE :default_profile END "
                    "ORDER BY candidate.candidate_id,candidate.version"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "sources": source_ids,
                    "default_profile": default_profile,
                },
            )
            .mappings()
            .all()
        )
        kind = "project_field" if table == "project_field_candidates" else "work_type"
        return IndustrialUnderstandingRepository._apply_reviews(
            session,
            claimed,
            kind,
            [dict(row) for row in rows],
        )

    @staticmethod
    def _work_child_rows(
        session: Session, claimed: ClaimedJob, table: str, source_ids: list[UUID]
    ) -> list[dict[str, Any]]:
        if table not in {"quantity_candidates", "material_candidates"}:
            raise ValueError("invalid child relation")
        rows = (
            session.execute(
                sa.text(
                    "WITH selected_profiles AS (SELECT DISTINCT ON (result.source_version_id) "
                    "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                    "result.profile_version) AS semantic_profile FROM workspace.project_understanding_stage_results "
                    "result JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                    "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                    "WHERE result.organization_id=:o AND result.workspace_id=:w "
                    "AND result.source_version_id=ANY(:sources) "
                    "AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                    "AND result.terminal_status IN ('complete','partial') ORDER BY result.source_version_id,"
                    "result.recorded_at DESC,result.stage_result_id DESC) "
                    f"SELECT child.* FROM workspace.{table} child JOIN workspace.work_type_candidates work "
                    "ON work.organization_id=child.organization_id AND work.workspace_id=child.workspace_id "
                    "AND work.candidate_id=child.work_candidate_id AND work.version=child.work_candidate_version "
                    "JOIN selected_profiles selected ON selected.source_version_id=work.source_version_id "
                    "WHERE child.organization_id=:o AND child.workspace_id=:w AND "
                    "work.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                    "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE :work_profile END "
                    "ORDER BY child.candidate_id,child.version"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "sources": source_ids,
                    "work_profile": WORK_EXTRACTION_PROFILE_VERSION,
                },
            )
            .mappings()
            .all()
        )
        kind = "quantity" if table == "quantity_candidates" else "material"
        return IndustrialUnderstandingRepository._apply_reviews(
            session,
            claimed,
            kind,
            [dict(row) for row in rows],
        )

    @staticmethod
    def _current_structure_rows(
        session: Session, claimed: ClaimedJob, source_ids: list[UUID]
    ) -> list[dict[str, Any]]:
        rows = session.execute(
            sa.text(
                "WITH selected_profiles AS (SELECT DISTINCT ON (result.source_version_id) "
                "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                "result.profile_version) AS semantic_profile FROM workspace.project_understanding_stage_results "
                "result JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                "WHERE result.organization_id=:o AND result.workspace_id=:w "
                "AND result.source_version_id=ANY(:sources) "
                "AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                "AND result.terminal_status IN ('complete','partial') ORDER BY result.source_version_id,"
                "result.recorded_at DESC,result.stage_result_id DESC) "
                "SELECT node.* FROM workspace.project_structure_node_versions node JOIN "
                "workspace.source_locators locator ON locator.organization_id=node.organization_id "
                "AND locator.workspace_id=node.workspace_id AND locator.source_locator_id=node.source_locator_id "
                "JOIN selected_profiles selected ON selected.source_version_id=locator.source_version_id "
                "WHERE node.organization_id=:o AND node.workspace_id=:w AND "
                "node.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE :default_profile END "
                "ORDER BY node.structure_node_id,node.version"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "sources": source_ids,
                "default_profile": PROJECT_EXTRACTION_PROFILE_VERSION,
            },
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    def _current_structure_relationship_rows(
        session: Session, claimed: ClaimedJob, source_ids: list[UUID]
    ) -> list[dict[str, Any]]:
        rows = session.execute(
            sa.text(
                "WITH selected_profiles AS (SELECT DISTINCT ON (result.source_version_id) "
                "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                "result.profile_version) AS semantic_profile FROM workspace.project_understanding_stage_results "
                "result JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                "WHERE result.organization_id=:o AND result.workspace_id=:w "
                "AND result.source_version_id=ANY(:sources) "
                "AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                "AND result.terminal_status IN ('complete','partial') ORDER BY result.source_version_id,"
                "result.recorded_at DESC,result.stage_result_id DESC) "
                "SELECT relationship.* FROM workspace.project_structure_relationship_candidates relationship "
                "JOIN selected_profiles selected ON selected.source_version_id=relationship.source_version_id "
                "WHERE relationship.organization_id=:o AND relationship.workspace_id=:w AND "
                "relationship.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE :default_profile END "
                "ORDER BY relationship.relationship_candidate_id,relationship.version"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "sources": source_ids,
                "default_profile": PROJECT_EXTRACTION_PROFILE_VERSION,
            },
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    def _materialization_input_digest(
        *,
        fields: list[dict[str, Any]],
        works: list[dict[str, Any]],
        quantities: list[dict[str, Any]],
        materials: list[dict[str, Any]],
        structures: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        defects: list[dict[str, Any]],
    ) -> str:
        """Fingerprint selected candidates, not only the source manifest.

        A source can receive an accepted replacement batch after an earlier
        assembly.  The immutable run identity must then change so API/UI output
        cannot retain a stale candidate projection.
        """

        def receipts(values: list[dict[str, Any]]) -> list[str]:
            return sorted(
                str(
                    value.get("candidate_digest")
                    or value.get("fingerprint")
                    or f"{value.get('candidate_id', value.get('structure_node_id', value.get('relationship_candidate_id', value.get('defect_id'))))}:{value.get('version')}"
                )
                for value in values
            )

        return semantic_digest(
            {
                "fields": receipts(fields),
                "works": receipts(works),
                "quantities": receipts(quantities),
                "materials": receipts(materials),
                "structures": receipts(structures),
                "relationships": receipts(relationships),
                "defects": receipts(defects),
            }
        )

    @staticmethod
    def _apply_reviews(
        session: Session,
        claimed: ClaimedJob,
        candidate_kind: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        decisions = session.execute(
            sa.text(
                "SELECT DISTINCT ON (candidate_id) candidate_id,action,resolved_value FROM "
                "workspace.project_candidate_review_decisions WHERE organization_id=:o AND "
                "workspace_id=:w AND candidate_kind=:kind ORDER BY candidate_id,decision_version DESC"
            ),
            {"o": claimed.organization_id, "w": claimed.workspace_id, "kind": candidate_kind},
        ).mappings()
        by_candidate = {str(item["candidate_id"]): dict(item) for item in decisions}
        result: list[dict[str, Any]] = []
        for row in rows:
            decision = by_candidate.get(str(row["candidate_id"]))
            if decision is None or decision["action"] == "confirmed":
                result.append(row)
                continue
            if decision["action"] == "rejected":
                continue
            resolved = decision["resolved_value"]
            if candidate_kind == "project_field":
                row["raw_value"] = str(resolved)
                row["normalized_value"] = resolved
                row["status"] = "verified"
            elif candidate_kind == "work_type":
                row["raw_name"] = str(resolved)
                row["normalized_name"] = " ".join(str(resolved).split()).casefold()
            elif candidate_kind == "quantity":
                row["raw_value"] = str(resolved)
                try:
                    row["parsed_value"] = Decimal(str(resolved))
                    row["normalized_value"] = Decimal(str(resolved))
                    row["status"] = "verified"
                except ArithmeticError:
                    row["status"] = "needs_evidence"
            elif candidate_kind == "material":
                row["raw_name"] = str(resolved)
                row["normalized_name"] = " ".join(str(resolved).split()).casefold()
                row["status"] = "verified"
            result.append(row)
        return result

    @staticmethod
    def _current_defects(
        session: Session, claimed: ClaimedJob, source_ids: list[UUID]
    ) -> list[dict[str, Any]]:
        rows = (
            session.execute(
                sa.text(
                    "WITH selected_profiles AS (SELECT DISTINCT ON (result.source_version_id) "
                    "result.source_version_id,COALESCE(job.provenance->>'engineering_semantic_profile',"
                    "result.profile_version) AS semantic_profile FROM workspace.project_understanding_stage_results "
                    "result JOIN workspace.durable_jobs job ON job.organization_id=result.organization_id "
                    "AND job.workspace_id=result.workspace_id AND job.job_id=result.job_id "
                    "WHERE result.organization_id=:o AND result.workspace_id=:w "
                    "AND result.source_version_id=ANY(:sources) "
                    "AND result.stage_kind='PROJECT_DEFINITION_EXTRACTION' "
                    "AND result.terminal_status IN ('complete','partial') ORDER BY result.source_version_id,"
                    "result.recorded_at DESC,result.stage_result_id DESC) SELECT defect.* FROM "
                    "workspace.project_reconciliation_defects defect WHERE defect.organization_id=:o "
                    "AND defect.workspace_id=:w AND defect.status='open' AND EXISTS (SELECT 1 FROM "
                    "workspace.source_locators locator JOIN selected_profiles selected ON "
                    "selected.source_version_id=locator.source_version_id WHERE "
                    "locator.organization_id=defect.organization_id AND locator.workspace_id=defect.workspace_id "
                    "AND locator.source_locator_id=ANY(defect.source_locator_ids) AND "
                    "defect.extraction_profile_version=CASE WHEN selected.semantic_profile LIKE "
                    "'qwen-engineering-extraction-%' THEN selected.semantic_profile ELSE :default_profile END) "
                    "ORDER BY defect.defect_id,defect.version"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "sources": source_ids,
                    "default_profile": PROJECT_EXTRACTION_PROFILE_VERSION,
                },
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    def _assemble_project_definition(
        self,
        session: Session,
        claimed: ClaimedJob,
        source_ids: list[UUID],
        fields: list[dict[str, Any]],
        corpus_digest: str,
    ) -> tuple[UUID, str, list[str], dict[str, Any]]:
        # Engineering extraction deliberately retains measurements, materials and
        # facility properties as generic field observations.  They are not safe
        # project-wide attributes merely because their extraction batch happened
        # to use the same ``field_key``.  Treating every such observation as a
        # project-definition key made unrelated dimensions and equipment values
        # manufacture thousands of false project conflicts, hiding an otherwise
        # useful partial model.  Keep those candidates for the later
        # evidence/scope reconciliation; only identity fields belong here.
        project_identity_keys = frozenset({"object_name", "purpose", "object_composition"})
        by_key: dict[str, list[dict[str, Any]]] = {}
        for item in fields:
            key = str(item["field_key"])
            if key in project_identity_keys:
                by_key.setdefault(key, []).append(item)
        selected: dict[str, Any] = {}
        gaps: list[str] = []
        for key, candidates in sorted(by_key.items()):
            normalized = {
                json.dumps(item["normalized_value"], sort_keys=True) for item in candidates
            }
            decision_id = deterministic_uuid(f"project-field-decision:{claimed.workspace_id}:{key}")
            if len(normalized) == 1:
                candidate = candidates[0]
                status = "verified"
                selected[key] = {
                    "raw_value": candidate["raw_value"],
                    "normalized_value": candidate["normalized_value"],
                    "source_version_id": str(candidate["source_version_id"]),
                    "source_locator_id": str(candidate["source_locator_id"]),
                    "candidate_id": str(candidate["candidate_id"]),
                }
                selected_id = candidate["candidate_id"]
                selected_version = candidate["version"]
            else:
                status = "conflict"
                selected_id = None
                selected_version = None
                gaps.append(f"PROJECT_FIELD_CONFLICT:{key}")
            receipt = semantic_digest(
                {
                    "key": key,
                    "candidates": [str(item["candidate_id"]) for item in candidates],
                    "status": status,
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.project_field_decisions "
                    "(organization_id,workspace_id,decision_id,decision_version,field_key,selected_candidate_id,"
                    "selected_candidate_version,status,validation_profile_version,decision_receipt_digest) VALUES "
                    "(:o,:w,:decision,1,:key,:candidate,:candidate_version,:status,'project-field-validator-v0.1',"
                    ":receipt) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "decision": decision_id,
                    "key": key,
                    "candidate": selected_id,
                    "candidate_version": selected_version,
                    "status": status,
                    "receipt": receipt,
                },
            )
        for required in ("object_name", "purpose", "object_composition"):
            if required not in selected:
                gaps.append(f"PROJECT_FIELD_GAP:{required}")
        definition = {
            "fields": selected,
            "gaps": sorted(gaps),
            "complete": not gaps,
            "authority": "workspace_verified_facts_only",
        }
        project_id = deterministic_uuid(
            f"project-definition:{claimed.organization_id}:{claimed.workspace_id}:{corpus_digest}"
        )
        fingerprint = semantic_digest(
            {
                "project_definition_id": str(project_id),
                "source_version_ids": [str(item) for item in source_ids],
                "definition": definition,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.project_definition_versions "
                "(organization_id,workspace_id,project_definition_id,version,purpose,object_class,"
                "source_version_ids,definition,fingerprint,created_at) VALUES "
                "(:o,:w,:project,1,:purpose,:object_class,:sources,CAST(:definition AS jsonb),:fingerprint,"
                "CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "project": project_id,
                "purpose": str(selected.get("purpose", {}).get("normalized_value", "unresolved")),
                "object_class": str(
                    selected.get("printed_class", {}).get("normalized_value", "unresolved")
                ),
                "sources": source_ids,
                "definition": _json(definition),
                "fingerprint": fingerprint,
            },
        )
        return (
            project_id,
            fingerprint,
            gaps,
            {key: value["normalized_value"] for key, value in selected.items()},
        )

    def _assemble_work_packages(
        self,
        session: Session,
        claimed: ClaimedJob,
        project_id: UUID,
        works: list[dict[str, Any]],
        quantities: list[dict[str, Any]],
        materials: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        packages: list[dict[str, Any]] = []
        for consolidated in consolidate_work_package_candidates(works, quantities, materials):
            observations = list(consolidated["observations"])
            work = observations[0]
            work_id = str(work["candidate_id"])
            package_id = deterministic_uuid(f"construction-work-package:{project_id}:{work_id}")
            mapping_status = str(work["canonical_mapping_status"])
            uncertainties = list(consolidated["uncertainties"])
            package = {
                "work_package_id": str(package_id),
                "version": 1,
                "work_candidate_id": work_id,
                "work_type": {
                    "raw": work["raw_name"],
                    "normalized": work["normalized_name"],
                    "mapping_status": mapping_status,
                },
                "scope": consolidated["scope_key"],
                "candidate_observation_ids": [str(item["candidate_id"]) for item in observations],
                "candidate_observation_count": len(observations),
                "quantities": [_plain(item) for item in consolidated["quantities"]],
                "materials": [_plain(item) for item in consolidated["materials"]],
                "source_locator_ids": list(consolidated["source_locator_ids"]),
                "uncertainties": uncertainties,
                "complete": mapping_status == "resolved" and not uncertainties,
            }
            fingerprint = semantic_digest(package)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.construction_work_package_versions "
                    "(organization_id,workspace_id,work_package_id,version,project_definition_id,"
                    "project_definition_version,work_type_key,work_type_version,package,fingerprint,created_at) "
                    "VALUES (:o,:w,:package,1,:project,1,:work_type,'unresolved-catalog@0',CAST(:document AS jsonb),"
                    ":fingerprint,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "package": package_id,
                    "project": project_id,
                    "work_type": str(work["normalized_name"]),
                    "document": _json(package),
                    "fingerprint": fingerprint,
                },
            )
            packages.append({**package, "fingerprint": fingerprint})
        return packages

    @staticmethod
    def _assemble_pd_rd_profile(
        session: Session,
        claimed: ClaimedJob,
        project_id: UUID,
        dimensions: dict[str, Any],
    ) -> dict[str, Any]:
        raw_date = dimensions.get("applicable_date")
        try:
            applicable_on = date.fromisoformat(str(raw_date)) if raw_date else None
        except ValueError:
            applicable_on = None
        rows: list[dict[str, Any]] = []
        if applicable_on is not None:
            rows = [
                dict(row)
                for row in session.execute(
                    sa.text(
                        "SELECT rv.rule_version_id,rv.output_contract,e.normative_edition_id,"
                        "e.official_catalog_url,p.normative_provision_id,p.version AS provision_version,"
                        "p.source_version_id,p.structural_path,p.content_digest,sl.source_locator_id,"
                        "sl.locator_value,ap.required_inputs,"
                        "ap.predicate FROM platform.rule_versions rv JOIN LATERAL (SELECT status "
                        "FROM platform.rule_version_states s WHERE s.rule_version_id=rv.rule_version_id "
                        "ORDER BY state_sequence DESC LIMIT 1) state ON true JOIN "
                        "platform.rule_normative_provision_evidence re ON "
                        "re.rule_version_id=rv.rule_version_id JOIN platform.normative_provision_versions p "
                        "ON p.normative_provision_id=re.normative_provision_id AND "
                        "p.version=re.normative_provision_version AND p.verification_status='verified' "
                        "JOIN platform.normative_editions e ON "
                        "e.normative_edition_id=re.normative_edition_id JOIN platform.source_locators sl "
                        "ON sl.source_locator_id=re.source_locator_id JOIN "
                        "platform.normative_applicability_predicates ap ON "
                        "ap.applicability_predicate_id=re.applicability_predicate_id AND "
                        "ap.version=re.applicability_predicate_version WHERE state.status='active' AND "
                        "(rv.effective_from IS NULL OR rv.effective_from<=:as_of) AND "
                        "(rv.effective_to IS NULL OR rv.effective_to>:as_of) ORDER BY "
                        "rv.rule_version_id,p.normative_provision_id,p.version"
                    ),
                    {"as_of": applicable_on},
                )
                .mappings()
                .all()
            ]
        context = PdRdProfileContext(
            claimed.organization_id,
            claimed.workspace_id,
            project_id,
            1,
            applicable_on,
            dimensions,
        )
        evaluated = evaluate_pd_rd_requirements(
            rows=rows,
            dimensions=dimensions,
            applicable_on=applicable_on,
            input_fingerprint=context.input_fingerprint,
            corpus_denominator=load_spds_corpus_denominator(session),
        )
        profile_id = deterministic_uuid(
            f"pd-rd-normative-profile:{claimed.workspace_id}:{project_id}:1:"
            f"{context.input_fingerprint}"
        )
        status = (
            "blocked" if any(bool(item.get("blocking")) for item in evaluated.gaps) else "complete"
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.applicable_pd_rd_normative_profiles "
                "(organization_id,workspace_id,profile_id,version,project_definition_id,"
                "project_definition_version,applicable_on,input_fingerprint,corpus_denominator,"
                "normative_edition_ids,"
                "rule_version_ids,required_pd_sections,expected_rd_sets,formatting_requirements,"
                "unresolved_inputs,gaps,completeness_status,semantic_fingerprint,created_at) VALUES "
                "(:o,:w,:profile,1,:project,1,:as_of,:input,CAST(:denominator AS jsonb),:editions,"
                ":rules,CAST(:required AS jsonb),"
                "CAST(:sets AS jsonb),CAST(:formatting AS jsonb),:unresolved,CAST(:gaps AS jsonb),"
                ":status,:fingerprint,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "profile": profile_id,
                "project": project_id,
                "as_of": applicable_on,
                "input": context.input_fingerprint,
                "denominator": _json(evaluated.corpus_denominator),
                "editions": list(evaluated.normative_edition_ids),
                "rules": list(evaluated.rule_version_ids),
                "required": _json(evaluated.required_pd_sections),
                "sets": _json(evaluated.expected_rd_sets),
                "formatting": _json(evaluated.formatting_requirements),
                "unresolved": list(evaluated.unresolved_inputs),
                "gaps": _json(evaluated.gaps),
                "status": status,
                "fingerprint": evaluated.semantic_fingerprint,
            },
        )
        return {
            "profile_id": str(profile_id),
            "version": 1,
            "semantic_fingerprint": evaluated.semantic_fingerprint,
            "normative_edition_ids": [str(item) for item in evaluated.normative_edition_ids],
            "rule_version_ids": [str(item) for item in evaluated.rule_version_ids],
            "required_pd_sections": list(evaluated.required_pd_sections),
            "expected_rd_sets": list(evaluated.expected_rd_sets),
            "formatting_requirements": list(evaluated.formatting_requirements),
            "gaps": list(evaluated.gaps),
            "denominator": evaluated.corpus_denominator,
        }

    @staticmethod
    def _assemble_matrix(
        session: Session,
        claimed: ClaimedJob,
        project_id: UUID,
        packages: list[dict[str, Any]],
        corpus_digest: str,
        normative_profile: dict[str, Any],
    ) -> tuple[UUID, str]:
        matrix_id = deterministic_uuid(f"work-requirement-matrix:{project_id}:{corpus_digest}")
        rows = [
            {
                "work_package_id": package["work_package_id"],
                "workspace_facts": package["source_locator_ids"],
                "practice_guidance": [],
                "verified_ntd": [
                    *normative_profile["required_pd_sections"],
                    *normative_profile["expected_rd_sets"],
                    *normative_profile["formatting_requirements"],
                ],
                "qualified_rules": normative_profile["rule_version_ids"],
                "customer_additions": [],
                "gaps": [
                    *[str(item["code"]) for item in normative_profile["gaps"]],
                    *[str(item) for item in package["uncertainties"]],
                ],
                "complete": not normative_profile["gaps"] and bool(package["complete"]),
            }
            for package in packages
        ]
        matrix = {
            "matrix_id": str(matrix_id),
            "version": 1,
            "project_definition_id": str(project_id),
            "rows": rows,
            "complete": bool(rows) and all(bool(item["complete"]) for item in rows),
            "authority_layers": {
                "workspace_facts": "available",
                "methodological_practice": "advisory_only",
                "normative_authority": (
                    "verified_subset" if normative_profile["normative_edition_ids"] else "gap"
                ),
                "deterministic_rules": (
                    "qualified_subset" if normative_profile["rule_version_ids"] else "gap"
                ),
            },
            "pd_rd_normative_profile": {
                "profile_id": normative_profile["profile_id"],
                "version": normative_profile["version"],
                "semantic_fingerprint": normative_profile["semantic_fingerprint"],
                "denominator": normative_profile["denominator"],
                "gaps": normative_profile["gaps"],
            },
        }
        fingerprint = semantic_digest(matrix)
        session.execute(
            sa.text(
                "INSERT INTO workspace.work_requirement_matrix_versions "
                "(organization_id,workspace_id,matrix_id,version,project_definition_id,"
                "project_definition_version,rule_set_version_id,matrix,fingerprint,created_at) VALUES "
                "(:o,:w,:matrix,1,:project,1,NULL,CAST(:document AS jsonb),:fingerprint,CURRENT_TIMESTAMP) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "matrix": matrix_id,
                "project": project_id,
                "document": _json(matrix),
                "fingerprint": fingerprint,
            },
        )
        return matrix_id, fingerprint

    @staticmethod
    def _select_json_rows(
        session: Session, table: str, organization_id: Any, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        allowed = {
            "project_field_candidates",
            "work_type_candidates",
            "quantity_candidates",
            "material_candidates",
            "project_reconciliation_defects",
        }
        if table not in allowed:
            raise ValueError("invalid snapshot relation")
        rows = (
            session.execute(
                sa.text(
                    f"SELECT * FROM workspace.{table} WHERE organization_id=:o AND workspace_id=:w "
                    "ORDER BY 1,2,3,4"
                ),
                {"o": organization_id, "w": workspace_id},
            )
            .mappings()
            .all()
        )
        return [_plain(dict(row)) for row in rows]

    @contextmanager
    def _session(self, claimed: ClaimedJob) -> Iterator[Session]:
        with Session(self._engine, autoflush=False, expire_on_commit=False) as session:
            with session.begin():
                _set_scope(session, claimed.organization_id, claimed.workspace_id)
                yield session

    @staticmethod
    def _document_id(claimed: ClaimedJob) -> UUID:
        return UUID(str(claimed.input_manifest["document_id"]))

    @staticmethod
    def _document_version(claimed: ClaimedJob) -> int:
        return int(claimed.input_manifest["document_version"])

    @staticmethod
    def _source_version_id(claimed: ClaimedJob) -> UUID:
        return UUID(str(claimed.input_manifest["source_version_id"]))


def _set_scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _json(value: object) -> str:
    return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_plain(item) for item in value]
    if isinstance(value, (UUID, date, datetime, Decimal, StrEnum)):
        return str(value)
    return value
