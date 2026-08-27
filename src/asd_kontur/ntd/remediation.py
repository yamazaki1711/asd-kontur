"""Canonical persistence for NTD-SEED-REMEDIATION-01."""

# ruff: noqa: E501,RUF001 -- SQL and Russian identity normalization remain auditable here.

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import deterministic_uuid
from asd_kontur.harness.models import digest_of
from asd_kontur.ntd.identifiers import NormalizedNormativeIdentifier, normalize_identifier
from asd_kontur.ntd.manifest import _resolve_undated_order_occurrences
from asd_kontur.ntd.models import (
    NormativeProvisionCandidate,
    NormativeProvisionKind,
    NormativeProvisionVersion,
    ProvisionVerificationStatus,
)

from .file_processing import (
    ArtifactValidation,
    ProvisionSemantics,
    RepresentationPage,
    StructuralFragment,
    extract_critical_tokens,
)
from .manifest import PracticeGuideNormativeReference
from .polza import PolzaPageCandidate
from .postgres import NtdRepository

NTD_SEED_REMEDIATION_KEY = "NTD-SEED-REMEDIATION-01"
HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT = (
    "sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6"
)


@dataclass(frozen=True, slots=True)
class ReconciledSeedIdentity:
    canonical_stable_identity_key: str
    legacy_stable_identity_keys: tuple[str, ...]
    normalized: NormalizedNormativeIdentifier
    reference_ids: tuple[UUID, ...]
    printed_designations: tuple[str, ...]
    printed_editions: tuple[str, ...]
    title_hints: tuple[str, ...]
    document_kind: str

    @property
    def reconciliation_id(self) -> UUID:
        return deterministic_uuid(
            f"ntd-seed-remediation-identity:{self.canonical_stable_identity_key}"
        )


@dataclass(frozen=True, slots=True)
class NativeProvisionQualification:
    provision_id: UUID
    provision_version: int
    verification_id: UUID
    normative_edition_id: UUID
    source_version_id: UUID
    normative_artifact_id: UUID
    artifact_digest: str
    structural_path: str
    source_locator_ids: tuple[UUID, ...]
    page_numbers: tuple[int, ...]
    critical_tokens: tuple[str, ...]
    verification_fingerprint: str
    provision_fingerprint: str
    reused: bool


@dataclass(frozen=True, slots=True)
class ExternalProvisionQualification:
    provision_id: UUID
    provision_version: int
    verification_id: UUID
    normative_edition_id: UUID
    source_version_id: UUID
    normative_artifact_id: UUID
    artifact_digest: str
    structural_path: str
    page_number: int
    source_region: tuple[float, float, float, float]
    full_receipt_id: UUID
    crop_receipt_id: UUID
    critical_tokens: tuple[str, ...]
    verification_fingerprint: str
    provision_fingerprint: str
    reused: bool


def load_historical_seed_identities(path: Path) -> tuple[ReconciledSeedIdentity, ...]:
    """Load the immutable 37-mention receipt and reconcile only identity semantics."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        data.get("raw_mention_count") != 37
        or data.get("identity_count") != 25
        or data.get("fingerprint") != HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT
    ):
        raise ValueError("NTD_SEED_HISTORICAL_MANIFEST_MISMATCH")
    references: list[PracticeGuideNormativeReference] = []
    legacy_by_reference: dict[UUID, str] = {}
    for value in data["references"]:
        reference_id = UUID(value["reference_id"])
        legacy_by_reference[reference_id] = str(value["normalized"]["stable_identity_key"])
        region_values = tuple(float(item) for item in value["region"])
        if len(region_values) != 4:
            raise ValueError("NTD_SEED_REFERENCE_REGION_INVALID")
        region = (region_values[0], region_values[1], region_values[2], region_values[3])
        references.append(
            PracticeGuideNormativeReference(
                reference_id,
                UUID(value["practice_guide_edition_id"]),
                UUID(value["source_version_id"]),
                int(value["pdf_page"]),
                region,
                int(value["occurrence_ordinal"]),
                str(value["raw_designation"]),
                value["raw_title"],
                str(value["raw_context"]),
                normalize_identifier(str(value["raw_designation"])),
                str(value["extraction_method"]),
                str(value["extraction_receipt_digest"]),
                str(value["source_fragment_digest"]),
                str(value["verification_status"]),
            )
        )
    references = _resolve_undated_order_occurrences(references)
    grouped: dict[str, list[PracticeGuideNormativeReference]] = {}
    for reference in references:
        grouped.setdefault(reference.normalized.stable_identity_key, []).append(reference)
    if len(grouped) != 25:
        raise ValueError("NTD_SEED_CANONICAL_IDENTITY_DENOMINATOR_MISMATCH")
    identities: list[ReconciledSeedIdentity] = []
    for identity_key, members in sorted(grouped.items()):
        selected = members[0].normalized
        identities.append(
            ReconciledSeedIdentity(
                identity_key,
                tuple(sorted({legacy_by_reference[item.reference_id] for item in members})),
                selected,
                tuple(item.reference_id for item in members),
                tuple(sorted({item.raw_designation for item in members})),
                tuple(
                    sorted(
                        {
                            item.normalized.printed_edition
                            for item in members
                            if item.normalized.printed_edition is not None
                        }
                    )
                ),
                tuple(sorted({item.raw_title for item in members if item.raw_title})),
                selected.document_kind.value,
            )
        )
    return tuple(identities)


class NtdRemediationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._ntd = NtdRepository(engine)

    def register_reopening_decision(
        self,
        *,
        canonical_commit: str,
        environment_fingerprint: str,
        decided_at: datetime,
        prior_receipt_fingerprints: tuple[str, ...],
    ) -> tuple[UUID, int]:
        decision_id = deterministic_uuid("decision:NTD-SEED-REMEDIATION-01")
        with Session(self._engine) as session, session.begin():
            seed = (
                session.execute(
                    sa.text(
                        "SELECT seed_manifest_id,version FROM platform.ntd_seed_manifests "
                        "WHERE manifest_fingerprint=:fingerprint"
                    ),
                    {"fingerprint": HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT},
                )
                .mappings()
                .one()
            )
            existing = session.execute(
                sa.text(
                    "SELECT version FROM platform.ntd_seed_remediation_decisions "
                    "WHERE remediation_decision_id=:id ORDER BY version DESC LIMIT 1"
                ),
                {"id": decision_id},
            ).scalar_one_or_none()
            if existing is not None:
                return decision_id, int(existing)
            payload = {
                "schema": "ntd-seed-remediation-decision-v1",
                "decision_key": NTD_SEED_REMEDIATION_KEY,
                "status": "in_progress",
                "logical_manifest_fingerprint": HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT,
                "reopened_defect_codes": (
                    "STALE_OFFICIAL_ACCESS_BLOCKED",
                    "MINSTROY_DISCOVERY_PAGINATION_INCOMPLETE",
                    "MINSTROY_EXACT_MATCH_NORMALIZATION_INCOMPLETE",
                    "LEGAL_ACT_IDENTITY_DATE_MISSING",
                ),
                "canonical_commit": canonical_commit,
                "environment_fingerprint": environment_fingerprint,
                "prior_receipt_fingerprints": prior_receipt_fingerprints,
            }
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_seed_remediation_decisions "
                    "(remediation_decision_id,version,prior_seed_manifest_id,prior_seed_manifest_version,"
                    "logical_manifest_fingerprint,decision_key,status,reopened_defect_codes,reason,"
                    "canonical_commit,environment_fingerprint,prior_receipt_fingerprints,"
                    "supersedes_version,decision_fingerprint,decided_at) VALUES "
                    "(:id,1,:seed,:seed_version,:manifest,:key,'in_progress',:defects,:reason,"
                    ":commit,:environment,:prior,NULL,:fingerprint,:decided)"
                ),
                {
                    "id": decision_id,
                    "seed": seed["seed_manifest_id"],
                    "seed_version": seed["version"],
                    "manifest": HISTORICAL_LOGICAL_MANIFEST_FINGERPRINT,
                    "key": NTD_SEED_REMEDIATION_KEY,
                    "defects": list(payload["reopened_defect_codes"]),
                    "reason": (
                        "The official Minstroy catalogue is reachable and exact records/artifacts "
                        "exist; the historical global access blocker is superseded by per-identity outcomes."
                    ),
                    "commit": canonical_commit,
                    "environment": environment_fingerprint,
                    "prior": list(prior_receipt_fingerprints),
                    "fingerprint": digest_of(payload),
                    "decided": decided_at,
                },
            )
        return decision_id, 1

    def register_identities(
        self,
        *,
        decision_id: UUID,
        decision_version: int,
        identities: tuple[ReconciledSeedIdentity, ...],
        recorded_at: datetime,
    ) -> None:
        if len(identities) != 25:
            raise ValueError("NTD_SEED_IDENTITY_DENOMINATOR_MISMATCH")
        with Session(self._engine) as session, session.begin():
            for identity in identities:
                payload = {
                    "schema": "ntd-seed-identity-reconciliation-v1",
                    "identity": identity.canonical_stable_identity_key,
                    "legacy": identity.legacy_stable_identity_keys,
                    "references": identity.reference_ids,
                    "printed_designations": identity.printed_designations,
                    "document_kind": identity.document_kind,
                }
                session.execute(
                    sa.text(
                        "INSERT INTO platform.ntd_seed_identity_reconciliations "
                        "(identity_reconciliation_id,remediation_decision_id,remediation_decision_version,"
                        "legacy_stable_identity_key,canonical_stable_identity_key,"
                        "practice_guide_reference_ids,printed_designations,identity_status,"
                        "decision_basis,reconciliation_fingerprint,recorded_at) VALUES "
                        "(:id,:decision,:version,:legacy,:canonical,:references,:designations,'resolved',"
                        "CAST(:basis AS jsonb),:fingerprint,:recorded) ON CONFLICT "
                        "(identity_reconciliation_id) DO NOTHING"
                    ),
                    {
                        "id": identity.reconciliation_id,
                        "decision": decision_id,
                        "version": decision_version,
                        "legacy": "|".join(identity.legacy_stable_identity_keys),
                        "canonical": identity.canonical_stable_identity_key,
                        "references": list(identity.reference_ids),
                        "designations": list(identity.printed_designations),
                        "basis": json.dumps(
                            {
                                "document_kind": identity.document_kind,
                                "printed_editions": identity.printed_editions,
                                "title_hints": identity.title_hints,
                                "order_identity_policy": "issuer+date+number+act_type",
                            },
                            ensure_ascii=False,
                        ),
                        "fingerprint": digest_of(payload),
                        "recorded": recorded_at,
                    },
                )

    def record_identity_resolution(
        self,
        *,
        identity: ReconciledSeedIdentity,
        provider: str,
        transport_profile: str,
        official_record_id: str | None,
        official_record_url: str | None,
        official_record_digest: str | None,
        resolution_status: str,
        failure_code: str | None,
        diagnostic: dict[str, Any],
        environment_fingerprint: str,
        recorded_at: datetime,
        normative_document_id: UUID | None = None,
        normative_edition_id: UUID | None = None,
        normative_artifact_ids: tuple[UUID, ...] = (),
    ) -> tuple[UUID, int]:
        resolution_id = deterministic_uuid(
            f"ntd-identity-resolution:{identity.canonical_stable_identity_key}:{provider}"
        )
        with Session(self._engine) as session, session.begin():
            latest = session.execute(
                sa.text(
                    "SELECT max(version) FROM platform.ntd_identity_resolution_versions "
                    "WHERE identity_resolution_id=:id"
                ),
                {"id": resolution_id},
            ).scalar_one()
            version = int(latest or 0) + 1
            payload = {
                "schema": "ntd-identity-resolution-v1",
                "resolution_id": resolution_id,
                "version": version,
                "identity": identity.canonical_stable_identity_key,
                "provider": provider,
                "transport_profile": transport_profile,
                "official_record_id": official_record_id,
                "official_record_url": official_record_url,
                "official_record_digest": official_record_digest,
                "status": resolution_status,
                "document": normative_document_id,
                "edition": normative_edition_id,
                "artifacts": normative_artifact_ids,
                "failure_code": failure_code,
                "diagnostic": diagnostic,
                "environment_fingerprint": environment_fingerprint,
            }
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_identity_resolution_versions "
                    "(identity_resolution_id,version,identity_reconciliation_id,provider,transport_profile,"
                    "official_record_id,official_record_url,official_record_digest,resolution_status,"
                    "normative_document_id,normative_edition_id,normative_artifact_ids,failure_code,"
                    "diagnostic,environment_fingerprint,supersedes_version,resolution_fingerprint,recorded_at) "
                    "VALUES (:id,:version,:identity,:provider,:transport,:record_id,:record_url,:record_digest,"
                    ":status,:document,:edition,:artifacts,:failure,CAST(:diagnostic AS jsonb),:environment,"
                    ":supersedes,:fingerprint,:recorded)"
                ),
                {
                    "id": resolution_id,
                    "version": version,
                    "identity": identity.reconciliation_id,
                    "provider": provider,
                    "transport": transport_profile,
                    "record_id": official_record_id,
                    "record_url": official_record_url,
                    "record_digest": official_record_digest,
                    "status": resolution_status,
                    "document": normative_document_id,
                    "edition": normative_edition_id,
                    "artifacts": list(normative_artifact_ids),
                    "failure": failure_code,
                    "diagnostic": json.dumps(diagnostic, ensure_ascii=False),
                    "environment": environment_fingerprint,
                    "supersedes": version - 1 if version > 1 else None,
                    "fingerprint": digest_of(payload),
                    "recorded": recorded_at,
                },
            )
        return resolution_id, version

    def record_artifact_validation(
        self,
        *,
        normative_artifact_id: UUID,
        source_version_id: UUID,
        declared_media_type: str | None,
        validation: ArtifactValidation,
        validated_at: datetime,
    ) -> UUID:
        validation_id = deterministic_uuid(
            f"ntd-artifact-validation:{normative_artifact_id}:{validation.fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_artifact_validations "
                    "(artifact_validation_id,normative_artifact_id,source_version_id,declared_media_type,"
                    "detected_media_type,byte_length,content_digest,representation_version,"
                    "encryption_status,signature_status,page_count,embedded_file_count,"
                    "active_content_status,title_identity_status,validation_status,observations,"
                    "validator_version,validation_fingerprint,validated_at) VALUES "
                    "(:id,:artifact,:source,:declared,:detected,:bytes,:digest,:representation,"
                    ":encryption,:signature,:pages,:embedded,:active,:title,:status,:observations,"
                    ":validator,:fingerprint,:validated) ON CONFLICT "
                    "(artifact_validation_id) DO NOTHING"
                ),
                {
                    "id": validation_id,
                    "artifact": normative_artifact_id,
                    "source": source_version_id,
                    "declared": declared_media_type,
                    "detected": validation.detected_media_type,
                    "bytes": validation.byte_length,
                    "digest": validation.content_digest,
                    "representation": validation.representation_version,
                    "encryption": validation.encryption_status,
                    "signature": validation.signature_status,
                    "pages": validation.page_count or None,
                    "embedded": validation.embedded_file_count,
                    "active": validation.active_content_status,
                    "title": validation.title_identity_status,
                    "status": validation.validation_status,
                    "observations": list(validation.observations),
                    "validator": "ntd-artifact-validation-v0.2",
                    "fingerprint": validation.fingerprint,
                    "validated": validated_at,
                },
            )
        return validation_id

    def record_representation_pages(
        self,
        *,
        normative_artifact_id: UUID,
        source_version_id: UUID,
        pages: tuple[RepresentationPage, ...],
        recorded_at: datetime,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            for page in pages:
                prior = (
                    session.execute(
                        sa.text(
                            "SELECT version,page_fingerprint FROM "
                            "platform.normative_representation_pages "
                            "WHERE normative_page_id=:id ORDER BY version DESC LIMIT 1"
                        ),
                        {"id": page.page_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                if prior is not None and prior["page_fingerprint"] == page.fingerprint:
                    continue
                version = 1 if prior is None else int(prior["version"]) + 1
                session.execute(
                    sa.text(
                        "INSERT INTO platform.normative_representation_pages "
                        "(normative_page_id,version,normative_artifact_id,source_version_id,page_index,"
                        "printed_page_label,representation_kind,width_points,height_points,"
                        "rotation_degrees,native_text_character_count,native_text_coverage,"
                        "render_digest,extraction_route,terminal_outcome,inventory_profile_version,"
                        "page_fingerprint,recorded_at,supersedes_version) "
                        "VALUES (:id,:version,:artifact,:source,:page,:label,:kind,:width,:height,:rotation,"
                        ":characters,:coverage,:render,:route,:outcome,:profile,:fingerprint,:recorded,"
                        ":supersedes)"
                    ),
                    {
                        "id": page.page_id,
                        "version": version,
                        "artifact": normative_artifact_id,
                        "source": source_version_id,
                        "page": page.page_index,
                        "label": page.printed_page_label,
                        "kind": page.kind,
                        "width": page.width_points,
                        "height": page.height_points,
                        "rotation": page.rotation_degrees,
                        "characters": page.native_text_character_count,
                        "coverage": page.native_text_coverage,
                        "render": page.render_digest,
                        "route": page.extraction_route,
                        "outcome": page.terminal_outcome,
                        "profile": page.inventory_profile_version,
                        "fingerprint": page.fingerprint,
                        "recorded": recorded_at,
                        "supersedes": version - 1 if version > 1 else None,
                    },
                )

    def find_external_page_candidate(
        self,
        *,
        normative_page_id: UUID,
        normative_page_version: int | None,
        provider_profile_version: str,
        prompt_version: str,
        schema_version: str,
        request_digest: str | None = None,
    ) -> dict[str, Any] | None:
        """Return an already paid page candidate without repeating the provider call."""

        with Session(self._engine) as session:
            row = (
                session.execute(
                    sa.text(
                        "SELECT request_digest,response_digest,status,retry_count,usage_receipt,"
                        "candidate_manifest,receipt_fingerprint FROM "
                        "platform.ntd_external_extraction_receipts WHERE normative_page_id=:page "
                        "AND (CAST(:version AS bigint) IS NULL OR normative_page_version=:version) "
                        "AND provider_profile_version=:profile AND prompt_version=:prompt "
                        "AND schema_version=:schema AND "
                        "(CAST(:request AS text) IS NULL OR request_digest=:request) "
                        "ORDER BY normative_page_version DESC LIMIT 1"
                    ),
                    {
                        "page": normative_page_id,
                        "version": normative_page_version,
                        "profile": provider_profile_version,
                        "prompt": prompt_version,
                        "schema": schema_version,
                        "request": request_digest,
                    },
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def record_external_page_candidate(
        self,
        *,
        normative_page_id: UUID,
        normative_page_version: int,
        candidate: PolzaPageCandidate,
        recorded_at: datetime,
    ) -> UUID:
        """Persist the redacted immutable provider receipt and structured candidate only."""

        receipt_id = deterministic_uuid(
            "ntd-external-extraction-receipt:"
            f"{normative_page_id}:{normative_page_version}:{candidate.provider_profile_version}:"
            f"{candidate.prompt_version}:{candidate.schema_version}:{candidate.request_digest}"
        )
        payload = {
            "schema": "ntd-external-extraction-receipt-v1",
            "receipt_id": receipt_id,
            "page": normative_page_id,
            "page_version": normative_page_version,
            "provider": "provider.external.polza",
            "model": candidate.provider_model,
            "profile": candidate.provider_profile_version,
            "prompt": candidate.prompt_version,
            "output_schema": candidate.schema_version,
            "request_digest": candidate.request_digest,
            "response_digest": candidate.response_digest,
            "retry_count": candidate.retry_count,
            "usage": candidate.usage_receipt,
            "candidate": candidate.candidate_manifest,
        }
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.ntd_external_extraction_receipts "
                    "(external_extraction_receipt_id,normative_page_id,normative_page_version,"
                    "provider_key,provider_model,provider_profile_version,prompt_version,schema_version,"
                    "request_digest,response_digest,status,retry_count,usage_receipt,candidate_manifest,"
                    "receipt_fingerprint,recorded_at) VALUES "
                    "(:id,:page,:version,'provider.external.polza',:model,:profile,:prompt,:schema,"
                    ":request,:response,'candidate',:retries,CAST(:usage AS jsonb),"
                    "CAST(:candidate AS jsonb),:fingerprint,:recorded) ON CONFLICT "
                    "(normative_page_id,normative_page_version,provider_profile_version,prompt_version,"
                    "schema_version,request_digest) DO NOTHING"
                ),
                {
                    "id": receipt_id,
                    "page": normative_page_id,
                    "version": normative_page_version,
                    "model": candidate.provider_model,
                    "profile": candidate.provider_profile_version,
                    "prompt": candidate.prompt_version,
                    "schema": candidate.schema_version,
                    "request": candidate.request_digest,
                    "response": candidate.response_digest,
                    "retries": candidate.retry_count,
                    "usage": json.dumps(candidate.usage_receipt, ensure_ascii=False),
                    "candidate": json.dumps(candidate.candidate_manifest, ensure_ascii=False),
                    "fingerprint": digest_of(payload),
                    "recorded": recorded_at,
                },
            )
        return receipt_id

    def persist_native_fragment_candidates(
        self,
        *,
        normative_edition_id: UUID,
        source_version_id: UUID,
        fragments: tuple[StructuralFragment, ...],
        recorded_at: datetime,
        verifier_identity: str,
    ) -> tuple[int, int]:
        with Session(self._engine) as session, session.begin():
            for fragment in fragments:
                locator_ids: list[UUID] = []
                for element in fragment.locators:
                    locator = element.locator
                    locator_ids.append(locator.source_locator_id)
                    session.execute(
                        sa.text(
                            "INSERT INTO platform.source_locators "
                            "(source_locator_id,source_version_id,locator_kind,locator_key,"
                            "locator_value,fragment_digest) VALUES "
                            "(:id,:source,'page_region',:key,CAST(:value AS jsonb),:digest) "
                            "ON CONFLICT (source_locator_id) DO NOTHING"
                        ),
                        {
                            "id": locator.source_locator_id,
                            "source": source_version_id,
                            "key": (
                                f"page={locator.page_number};region="
                                + ",".join(f"{value:.12f}" for value in locator.region)
                                + f";order={element.reading_order}"
                            ),
                            "value": json.dumps(
                                {"page": locator.page_number, "region": locator.region}
                            ),
                            "digest": locator.evidence_digest,
                        },
                    )
                if not locator_ids:
                    continue
                session.execute(
                    sa.text(
                        "INSERT INTO platform.structural_units "
                        "(structural_unit_id,normative_edition_id,parent_structural_unit_id,unit_type,"
                        "structural_path,ordinal,source_locator_id,normalized_text,content_digest) VALUES "
                        "(:id,:edition,NULL,:kind,:path,:ordinal,:locator,:text,:digest) "
                        "ON CONFLICT (structural_unit_id) DO NOTHING"
                    ),
                    {
                        "id": fragment.structural_id,
                        "edition": normative_edition_id,
                        "kind": fragment.unit_type,
                        "path": fragment.structural_path,
                        "ordinal": fragment.ordinal,
                        "locator": locator_ids[0],
                        "text": fragment.normalized_search_text,
                        "digest": fragment.fragment_digest,
                    },
                )
                fragment_id = deterministic_uuid(
                    f"ntd-structural-fragment:{fragment.structural_id}:{fragment.fingerprint}"
                )
                session.execute(
                    sa.text(
                        "INSERT INTO platform.normative_structural_fragments "
                        "(structural_fragment_id,structural_unit_id,source_version_id,source_locator_ids,"
                        "exact_heading,exact_number,raw_text,normalized_search_text,source_fragment_digest,"
                        "extraction_method,extraction_profile_version,extraction_lineage,"
                        "fragment_fingerprint,recorded_at) VALUES "
                        "(:id,:structural,:source,:locators,:heading,:number,:raw,:normalized,:digest,"
                        ":method,'ntd-structural-reconstruction-v0.1',CAST(:lineage AS jsonb),"
                        ":fingerprint,:recorded) ON CONFLICT (structural_fragment_id) DO NOTHING"
                    ),
                    {
                        "id": fragment_id,
                        "structural": fragment.structural_id,
                        "source": source_version_id,
                        "locators": locator_ids,
                        "heading": fragment.exact_heading,
                        "number": fragment.exact_number,
                        "raw": fragment.raw_text,
                        "normalized": fragment.normalized_search_text,
                        "digest": fragment.fragment_digest,
                        "method": fragment.extraction_method,
                        "lineage": json.dumps(
                            {"locator_ids": [str(value) for value in locator_ids]},
                            ensure_ascii=False,
                        ),
                        "fingerprint": fragment.fingerprint,
                        "recorded": recorded_at,
                    },
                )
        for fragment in fragments:
            if fragment.unit_type not in {
                "clause",
                "subclause",
                "item",
                "table",
                "form",
                "formula",
            }:
                continue
            if len(fragment.raw_text.strip()) < 15 or not fragment.locators:
                continue
            semantics = _semantics_for_fragment(fragment)
            candidate = _candidate_for_fragment(
                normative_edition_id=normative_edition_id,
                source_version_id=source_version_id,
                fragment=fragment,
            )
            self._ntd.register_provision_candidate(candidate)
            self._record_semantics(candidate, semantics, recorded_at=recorded_at)
            self._record_insufficient_verification(
                candidate,
                semantics,
                recorded_at=recorded_at,
                verifier_identity=verifier_identity,
            )
        return len(fragments), 0

    def _record_semantics(
        self,
        candidate: NormativeProvisionCandidate,
        semantics: ProvisionSemantics,
        *,
        recorded_at: datetime,
    ) -> None:
        fingerprint = digest_of(
            {
                "schema": "normative-provision-semantics-v1",
                "candidate": candidate.candidate_id,
                "version": candidate.candidate_version,
                "semantics": semantics,
            }
        )
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_semantics "
                    "(provision_candidate_id,candidate_version,normalized_proposition,subject,predicate,"
                    "object_value,modality,conditions,exclusions,applicability,units_dimensions,"
                    "referenced_designations,uncertainty_codes,semantics_fingerprint,recorded_at) VALUES "
                    "(:id,:version,CAST(:proposition AS jsonb),CAST(:subject AS jsonb),"
                    "CAST(:predicate AS jsonb),CAST(:object AS jsonb),:modality,CAST(:conditions AS jsonb),"
                    "CAST(:exclusions AS jsonb),CAST(:applicability AS jsonb),CAST(:units AS jsonb),"
                    ":references,:uncertainties,:fingerprint,:recorded) ON CONFLICT "
                    "(provision_candidate_id,candidate_version) DO NOTHING"
                ),
                {
                    "id": candidate.candidate_id,
                    "version": candidate.candidate_version,
                    "proposition": json.dumps(
                        {"verbatim_text_digest": candidate.content_digest}, ensure_ascii=False
                    ),
                    "subject": json.dumps(semantics.subject, ensure_ascii=False),
                    "predicate": json.dumps(semantics.predicate, ensure_ascii=False),
                    "object": json.dumps(semantics.object_value, ensure_ascii=False),
                    "modality": semantics.modality,
                    "conditions": json.dumps(semantics.conditions, ensure_ascii=False),
                    "exclusions": json.dumps(semantics.exclusions, ensure_ascii=False),
                    "applicability": json.dumps(semantics.applicability, ensure_ascii=False),
                    "units": json.dumps(semantics.units_dimensions, ensure_ascii=False),
                    "references": list(semantics.referenced_designations),
                    "uncertainties": list(semantics.uncertainty_codes),
                    "fingerprint": fingerprint,
                    "recorded": recorded_at,
                },
            )

    def _record_insufficient_verification(
        self,
        candidate: NormativeProvisionCandidate,
        semantics: ProvisionSemantics,
        *,
        recorded_at: datetime,
        verifier_identity: str,
    ) -> None:
        verification_id = deterministic_uuid(
            f"ntd-provision-verification:{candidate.candidate_id}:candidate-v1"
        )
        payload = {
            "schema": "ntd-provision-verification-v1",
            "candidate": candidate.candidate_id,
            "source_digest": candidate.content_digest,
            "critical_tokens": semantics.critical_tokens,
            "outcome": "insufficient",
            "reason": "DOCUMENT_TERMINAL_PAGE_AND_CRITICAL_TOKEN_GATE_PENDING",
        }
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_verification_outcomes "
                    "(provision_verification_id,provision_candidate_id,candidate_version,outcome,"
                    "critical_token_checks,structural_checks,conflict_refs,verification_method,"
                    "verifier_version,verification_fingerprint,verified_by_identity_id,verified_at) VALUES "
                    "(:id,:candidate,:version,'insufficient',CAST(:critical AS jsonb),"
                    "CAST(:structural AS jsonb),'[]'::jsonb,'candidate_source_preservation',"
                    "'ntd-candidate-verifier-v0.1',"
                    ":fingerprint,:verifier,:verified) ON CONFLICT (provision_verification_id) DO NOTHING"
                ),
                {
                    "id": verification_id,
                    "candidate": candidate.candidate_id,
                    "version": candidate.candidate_version,
                    "critical": json.dumps(
                        {
                            "tokens": semantics.critical_tokens,
                            "source_preserved": True,
                            "qualification_pending": True,
                        },
                        ensure_ascii=False,
                    ),
                    "structural": json.dumps(
                        {
                            "locator_present": True,
                            "edition_pinned": True,
                            "all_pages_terminal": False,
                        },
                        ensure_ascii=False,
                    ),
                    "fingerprint": digest_of(payload),
                    "verifier": verifier_identity,
                    "verified": recorded_at,
                },
            )

    def qualify_external_provision(
        self,
        *,
        designation: str,
        page_number: int,
        clause_number: str,
        full_profile_version: str,
        crop_profile_version: str,
        verified_at: datetime,
        verifier_identity: str,
    ) -> ExternalProvisionQualification:
        """Publish one raster provision only after full/crop exact-text consensus."""

        verifier_version = "ntd-polza-full-crop-consensus-verifier-v0.1"
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    sa.text(
                        "SELECT r.external_extraction_receipt_id,r.provider_profile_version,"
                        "r.provider_model,r.prompt_version,r.schema_version,r.request_digest,"
                        "r.response_digest,r.status,r.candidate_manifest,p.normative_page_id,"
                        "p.version AS page_version,p.page_index,p.normative_artifact_id,"
                        "p.source_version_id,na.normative_edition_id,na.content_digest AS "
                        "artifact_digest,av.validation_status,av.title_identity_status,"
                        "av.validation_fingerprint FROM platform.ntd_external_extraction_receipts r "
                        "JOIN platform.normative_representation_pages p ON "
                        "p.normative_page_id=r.normative_page_id AND "
                        "p.version=r.normative_page_version JOIN platform.normative_artifacts na "
                        "ON na.normative_artifact_id=p.normative_artifact_id JOIN "
                        "platform.normative_editions ne ON ne.normative_edition_id="
                        "na.normative_edition_id JOIN platform.normative_documents nd ON "
                        "nd.normative_document_id=ne.normative_document_id JOIN LATERAL "
                        "(SELECT value.* FROM platform.normative_artifact_validations value WHERE "
                        "value.normative_artifact_id=na.normative_artifact_id ORDER BY "
                        "value.validated_at DESC LIMIT 1) av ON true WHERE nd.designation="
                        ":designation AND p.page_index=:page AND "
                        "r.provider_profile_version=ANY(:profiles) ORDER BY r.recorded_at"
                    ),
                    {
                        "designation": designation,
                        "page": page_number,
                        "profiles": [full_profile_version, crop_profile_version],
                    },
                )
                .mappings()
                .all()
            )
        full_rows = [row for row in rows if row["provider_profile_version"] == full_profile_version]
        crop_rows = [
            row
            for row in rows
            if row["provider_profile_version"] == crop_profile_version
            and _blocks_for_clause(dict(row["candidate_manifest"]), clause_number)
        ]
        if len(full_rows) != 1 or len(crop_rows) != 1:
            raise ValueError("NTD_EXTERNAL_CONSENSUS_RECEIPTS_MISSING")
        full = full_rows[0]
        crop = crop_rows[0]
        if any(row["status"] != "candidate" for row in (full, crop)):
            raise ValueError("NTD_EXTERNAL_CONSENSUS_RECEIPT_NOT_CANDIDATE")
        if any(row["validation_status"] != "supported" for row in (full, crop)):
            raise ValueError("NTD_EXTERNAL_ARTIFACT_NOT_SUPPORTED")
        title_status = str(full["title_identity_status"])
        if title_status not in {"native_confirmed", "confirmed"} and not (
            title_status == "native_text_missing" and _external_title_consensus(rows, designation)
        ):
            raise ValueError("NTD_EXTERNAL_ARTIFACT_TITLE_NOT_CONFIRMED")
        identity_fields = (
            "normative_page_id",
            "page_index",
            "normative_artifact_id",
            "source_version_id",
            "normative_edition_id",
            "artifact_digest",
            "validation_fingerprint",
        )
        if any(full[field] != crop[field] for field in identity_fields):
            raise ValueError("NTD_EXTERNAL_CONSENSUS_LINEAGE_MISMATCH")

        full_manifest = dict(full["candidate_manifest"])
        crop_manifest = dict(crop["candidate_manifest"])
        full_blocks = _blocks_for_clause(full_manifest, clause_number)
        crop_blocks = _blocks_for_clause(crop_manifest, clause_number)
        if len(full_blocks) != 1 or not crop_blocks:
            raise ValueError("NTD_EXTERNAL_CONSENSUS_CLAUSE_NOT_UNIQUE")
        if any(block.get("ambiguity_flags") for block in (*full_blocks, *crop_blocks)):
            raise ValueError("NTD_EXTERNAL_CONSENSUS_AMBIGUOUS")
        full_text = _normalized_whitespace(str(full_blocks[0]["raw_transcription"]))
        crop_text = _normalized_whitespace(
            " ".join(str(block["raw_transcription"]) for block in crop_blocks)
        )
        if full_text != crop_text:
            raise ValueError("NTD_EXTERNAL_CONSENSUS_TEXT_MISMATCH")
        full_tokens = extract_critical_tokens(full_text)
        crop_tokens = extract_critical_tokens(crop_text)
        if full_tokens != crop_tokens:
            raise ValueError("NTD_EXTERNAL_CONSENSUS_CRITICAL_TOKEN_MISMATCH")
        region = _union_regions(crop_blocks)
        structural_path = f"external/page:{page_number}/clause:{clause_number}"
        content_digest = "sha256:" + hashlib.sha256(full_text.encode()).hexdigest()
        edition_id = UUID(str(full["normative_edition_id"]))
        source_version_id = UUID(str(full["source_version_id"]))
        candidate_id = deterministic_uuid(
            f"ntd-external-provision-candidate:{edition_id}:{structural_path}:{content_digest}"
        )
        model_provenance = {
            "schema": "ntd-polza-full-crop-consensus-lineage-v1",
            "provider_model": str(full["provider_model"]),
            "full_receipt_id": str(full["external_extraction_receipt_id"]),
            "crop_receipt_id": str(crop["external_extraction_receipt_id"]),
            "full_request_digest": str(full["request_digest"]),
            "full_response_digest": str(full["response_digest"]),
            "crop_request_digest": str(crop["request_digest"]),
            "crop_response_digest": str(crop["response_digest"]),
            "prompt_versions": [str(full["prompt_version"]), str(crop["prompt_version"])],
            "schema_versions": [str(full["schema_version"]), str(crop["schema_version"])],
        }
        candidate = NormativeProvisionCandidate(
            candidate_id,
            1,
            edition_id,
            source_version_id,
            structural_path,
            NormativeProvisionKind.CLAUSE,
            page_number,
            region,
            full_text,
            "vlm_bounded_region",
            "polza-full-crop-consensus-v0.1",
            content_digest,
            model_provenance,
        )
        self._ntd.register_provision_candidate(candidate)
        structural_unit_id = self._ntd.register_structural_unit_for_candidate(candidate)
        verification_payload = {
            "schema": "ntd-external-provision-verification-v1",
            "candidate_id": str(candidate_id),
            "artifact_digest": str(full["artifact_digest"]),
            "artifact_validation_fingerprint": str(full["validation_fingerprint"]),
            "edition_id": str(edition_id),
            "source_version_id": str(source_version_id),
            "page_number": page_number,
            "source_region": region,
            "structural_path": structural_path,
            "content_digest": content_digest,
            "critical_tokens": full_tokens,
            "full_receipt_id": str(full["external_extraction_receipt_id"]),
            "crop_receipt_id": str(crop["external_extraction_receipt_id"]),
            "verifier_version": verifier_version,
        }
        verification_fingerprint = digest_of(verification_payload)
        verification_id = deterministic_uuid(
            f"ntd-provision-verification:{candidate_id}:{verifier_version}:"
            f"{verification_fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT verification_fingerprint FROM "
                    "platform.normative_provision_verification_outcomes WHERE "
                    "provision_candidate_id=:candidate AND candidate_version=1 AND "
                    "verifier_version=:verifier"
                ),
                {"candidate": candidate_id, "verifier": verifier_version},
            ).scalar_one_or_none()
            if existing is not None and existing != verification_fingerprint:
                raise ValueError("NTD_EXTERNAL_VERIFICATION_REPLAY_CONFLICT")
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_verification_outcomes "
                    "(provision_verification_id,provision_candidate_id,candidate_version,outcome,"
                    "critical_token_checks,structural_checks,conflict_refs,verification_method,"
                    "verifier_version,verification_fingerprint,verified_by_identity_id,verified_at) "
                    "VALUES (:id,:candidate,1,'supported',CAST(:critical AS jsonb),"
                    "CAST(:structural AS jsonb),'[]'::jsonb,'external_full_crop_consensus',"
                    ":verifier,:fingerprint,:identity,:verified) ON CONFLICT "
                    "(provision_candidate_id,candidate_version,verifier_version) DO NOTHING"
                ),
                {
                    "id": verification_id,
                    "candidate": candidate_id,
                    "critical": json.dumps(
                        {"tokens": full_tokens, "full_crop_exact_text_consensus": True},
                        ensure_ascii=False,
                    ),
                    "structural": json.dumps(
                        {
                            "page_number": page_number,
                            "source_region": region,
                            "artifact_supported": True,
                            "edition_pinned": True,
                            "whole_document_completion_claimed": False,
                        }
                    ),
                    "verifier": verifier_version,
                    "fingerprint": verification_fingerprint,
                    "identity": verifier_identity,
                    "verified": verified_at,
                },
            )
        provision_id = deterministic_uuid(f"normative-provision:{edition_id}:{structural_path}")
        provision_fingerprint = digest_of(
            {
                "schema": "normative-provision-semantic-v1",
                "provision_id": provision_id,
                "version": 1,
                "edition_id": edition_id,
                "source_version_id": source_version_id,
                "structural_path": structural_path,
                "kind": NormativeProvisionKind.CLAUSE.value,
                "content_digest": content_digest,
                "verification_fingerprint": verification_fingerprint,
            }
        )
        reused = self._ntd.publish_provision(
            NormativeProvisionVersion(
                provision_id,
                1,
                candidate_id,
                1,
                edition_id,
                source_version_id,
                structural_path,
                NormativeProvisionKind.CLAUSE,
                page_number,
                region,
                full_text,
                content_digest,
                provision_fingerprint,
                ProvisionVerificationStatus.VERIFIED,
                f"ntd-provision-verification:{verification_id}",
                verifier_identity,
                verified_at,
            ),
            structural_unit_id=structural_unit_id,
        )
        return ExternalProvisionQualification(
            provision_id,
            1,
            verification_id,
            edition_id,
            source_version_id,
            UUID(str(full["normative_artifact_id"])),
            str(full["artifact_digest"]),
            structural_path,
            page_number,
            region,
            UUID(str(full["external_extraction_receipt_id"])),
            UUID(str(crop["external_extraction_receipt_id"])),
            full_tokens,
            verification_fingerprint,
            provision_fingerprint,
            reused,
        )

    def qualify_native_provision(
        self,
        *,
        normative_edition_id: UUID,
        source_version_id: UUID,
        structural_path: str,
        replay_fragment: StructuralFragment,
        expected_artifact_digest: str,
        verified_at: datetime,
        verifier_identity: str,
    ) -> NativeProvisionQualification:
        """Replay exact native evidence and publish one independently supported provision.

        This deliberately verifies only the source pages used by the provision.  It
        does not claim that the remaining artifact pages or the edition as a whole
        have completed recovery.
        """

        verifier_version = "ntd-native-deterministic-verifier-v0.2"
        with Session(self._engine) as session:
            row = (
                session.execute(
                    sa.text(
                        "SELECT pc.*,su.structural_unit_id,sf.source_locator_ids,sf.raw_text AS "
                        "fragment_raw_text,sf.source_fragment_digest,sf.fragment_fingerprint,"
                        "na.normative_artifact_id,na.content_digest AS artifact_digest,"
                        "na.official_url,av.validation_status,av.title_identity_status,"
                        "av.validation_fingerprint FROM platform.normative_provision_candidates pc "
                        "JOIN platform.structural_units su ON su.normative_edition_id="
                        "pc.normative_edition_id AND su.structural_path=pc.structural_path "
                        "JOIN platform.normative_structural_fragments sf ON "
                        "sf.structural_unit_id=su.structural_unit_id AND "
                        "sf.source_version_id=pc.source_version_id "
                        "JOIN platform.normative_artifacts na ON na.normative_edition_id="
                        "pc.normative_edition_id AND na.source_version_id=pc.source_version_id "
                        "JOIN LATERAL (SELECT value.* FROM platform.normative_artifact_validations "
                        "value WHERE value.normative_artifact_id=na.normative_artifact_id "
                        "ORDER BY value.validated_at DESC LIMIT 1) av ON true "
                        "WHERE pc.normative_edition_id=:edition AND pc.source_version_id=:source "
                        "AND pc.structural_path=:path ORDER BY pc.candidate_version DESC LIMIT 1"
                    ),
                    {
                        "edition": normative_edition_id,
                        "source": source_version_id,
                        "path": structural_path,
                    },
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueError("NTD_NATIVE_PROVISION_CANDIDATE_NOT_FOUND")
            locator_ids = tuple(UUID(str(value)) for value in row["source_locator_ids"])
            locators = (
                session.execute(
                    sa.text(
                        "SELECT source_locator_id,source_version_id,locator_value,fragment_digest "
                        "FROM platform.source_locators WHERE source_locator_id=ANY(:locators)"
                    ),
                    {"locators": list(locator_ids)},
                )
                .mappings()
                .all()
            )
            locator_by_id = {UUID(str(value["source_locator_id"])): value for value in locators}
            page_numbers = tuple(
                sorted(
                    {int(locator_by_id[value]["locator_value"]["page"]) for value in locator_ids}
                )
            )
            page_outcomes = (
                session.execute(
                    sa.text(
                        "SELECT DISTINCT ON (page_index) page_index,terminal_outcome,"
                        "extraction_route FROM platform.normative_representation_pages WHERE "
                        "normative_artifact_id=:artifact AND page_index=ANY(:pages) "
                        "ORDER BY page_index,version DESC"
                    ),
                    {
                        "artifact": row["normative_artifact_id"],
                        "pages": list(page_numbers),
                    },
                )
                .mappings()
                .all()
            )

        replay_locator_ids = tuple(
            element.locator.source_locator_id for element in replay_fragment.locators
        )
        if str(row["artifact_digest"]) != expected_artifact_digest:
            raise ValueError("NTD_NATIVE_ARTIFACT_DIGEST_MISMATCH")
        if row["validation_status"] != "supported" or row["title_identity_status"] not in {
            "native_confirmed",
            "confirmed",
        }:
            raise ValueError("NTD_NATIVE_ARTIFACT_NOT_SUPPORTED")
        if replay_fragment.structural_path != structural_path:
            raise ValueError("NTD_NATIVE_STRUCTURAL_PATH_MISMATCH")
        if (
            replay_fragment.raw_text != row["verbatim_text"]
            or replay_fragment.raw_text != row["fragment_raw_text"]
            or replay_fragment.fragment_digest != row["content_digest"]
            or replay_fragment.fragment_digest != row["source_fragment_digest"]
        ):
            raise ValueError("NTD_NATIVE_REPLAY_CONTENT_MISMATCH")
        if replay_locator_ids != locator_ids or len(locator_by_id) != len(locator_ids):
            raise ValueError("NTD_NATIVE_REPLAY_LOCATOR_MISMATCH")
        for element in replay_fragment.locators:
            stored = locator_by_id[element.locator.source_locator_id]
            locator_value = stored["locator_value"]
            if (
                UUID(str(stored["source_version_id"])) != source_version_id
                or int(locator_value["page"]) != element.locator.page_number
                or tuple(float(value) for value in locator_value["region"])
                != tuple(float(value) for value in element.locator.region)
                or str(stored["fragment_digest"]) != element.locator.evidence_digest
            ):
                raise ValueError("NTD_NATIVE_REPLAY_LOCATOR_EVIDENCE_MISMATCH")
        outcome_by_page = {
            int(value["page_index"]): (value["terminal_outcome"], value["extraction_route"])
            for value in page_outcomes
        }
        if set(outcome_by_page) != set(page_numbers) or any(
            outcome_by_page[page] != ("native_complete", "native") for page in page_numbers
        ):
            raise ValueError("NTD_NATIVE_SOURCE_PAGE_NOT_TERMINAL")

        semantics = _semantics_for_fragment(replay_fragment)
        verification_payload = {
            "schema": "ntd-native-provision-verification-v2",
            "candidate_id": str(row["provision_candidate_id"]),
            "candidate_version": int(row["candidate_version"]),
            "artifact_digest": expected_artifact_digest,
            "artifact_validation_fingerprint": str(row["validation_fingerprint"]),
            "source_version_id": str(source_version_id),
            "normative_edition_id": str(normative_edition_id),
            "structural_path": structural_path,
            "fragment_digest": replay_fragment.fragment_digest,
            "fragment_fingerprint": replay_fragment.fingerprint,
            "source_locator_ids": [str(value) for value in locator_ids],
            "page_numbers": page_numbers,
            "critical_tokens": semantics.critical_tokens,
            "page_outcomes": outcome_by_page,
            "verifier_version": verifier_version,
        }
        if semantics.uncertainty_codes:
            verification_payload["semantic_uncertainty_codes"] = semantics.uncertainty_codes
        verification_fingerprint = digest_of(verification_payload)
        verification_id = deterministic_uuid(
            f"ntd-provision-verification:{row['provision_candidate_id']}:"
            f"{verifier_version}:{verification_fingerprint}"
        )
        with Session(self._engine) as session, session.begin():
            existing_verification = session.execute(
                sa.text(
                    "SELECT verification_fingerprint FROM "
                    "platform.normative_provision_verification_outcomes WHERE "
                    "provision_candidate_id=:candidate AND candidate_version=:version "
                    "AND verifier_version=:verifier"
                ),
                {
                    "candidate": row["provision_candidate_id"],
                    "version": row["candidate_version"],
                    "verifier": verifier_version,
                },
            ).scalar_one_or_none()
            if (
                existing_verification is not None
                and existing_verification != verification_fingerprint
            ):
                raise ValueError("NTD_NATIVE_VERIFICATION_REPLAY_CONFLICT")
            session.execute(
                sa.text(
                    "INSERT INTO platform.normative_provision_verification_outcomes "
                    "(provision_verification_id,provision_candidate_id,candidate_version,outcome,"
                    "critical_token_checks,structural_checks,conflict_refs,verification_method,"
                    "verifier_version,verification_fingerprint,verified_by_identity_id,verified_at) "
                    "VALUES (:id,:candidate,:version,'supported',CAST(:critical AS jsonb),"
                    "CAST(:structural AS jsonb),'[]'::jsonb,'deterministic_native_replay',"
                    ":verifier,:fingerprint,:identity,:verified) ON CONFLICT "
                    "(provision_candidate_id,candidate_version,verifier_version) DO NOTHING"
                ),
                {
                    "id": verification_id,
                    "candidate": row["provision_candidate_id"],
                    "version": row["candidate_version"],
                    "critical": json.dumps(
                        {
                            "tokens": semantics.critical_tokens,
                            "source_replay_exact": True,
                            "numeric_or_modal_rewrite": False,
                        },
                        ensure_ascii=False,
                    ),
                    "structural": json.dumps(
                        {
                            "locator_ids": [str(value) for value in locator_ids],
                            "page_numbers": page_numbers,
                            "all_referenced_pages_terminal_native": True,
                            "whole_document_completion_claimed": False,
                            "semantic_interpretation_qualified": not semantics.uncertainty_codes,
                            "semantic_uncertainty_codes": semantics.uncertainty_codes,
                        },
                        ensure_ascii=False,
                    ),
                    "verifier": verifier_version,
                    "fingerprint": verification_fingerprint,
                    "identity": verifier_identity,
                    "verified": verified_at,
                },
            )

        provision_id = deterministic_uuid(
            f"normative-provision:{normative_edition_id}:{structural_path}"
        )
        provision_fingerprint = digest_of(
            {
                "schema": "normative-provision-semantic-v1",
                "provision_id": provision_id,
                "version": 1,
                "edition_id": normative_edition_id,
                "source_version_id": source_version_id,
                "structural_path": structural_path,
                "kind": str(row["provision_kind"]),
                "content_digest": str(row["content_digest"]),
                "verification_fingerprint": verification_fingerprint,
            }
        )
        region_values = tuple(float(value) for value in row["region"]) if row["region"] else None
        if region_values is not None and len(region_values) != 4:
            raise ValueError("NTD_NATIVE_PRIMARY_REGION_INVALID")
        region = (
            (region_values[0], region_values[1], region_values[2], region_values[3])
            if region_values is not None
            else None
        )
        provision = NormativeProvisionVersion(
            provision_id,
            1,
            UUID(str(row["provision_candidate_id"])),
            int(row["candidate_version"]),
            normative_edition_id,
            source_version_id,
            structural_path,
            NormativeProvisionKind(str(row["provision_kind"])),
            int(row["page_number"]) if row["page_number"] is not None else None,
            region,
            str(row["verbatim_text"]),
            str(row["content_digest"]),
            provision_fingerprint,
            ProvisionVerificationStatus.VERIFIED,
            f"ntd-provision-verification:{verification_id}",
            verifier_identity,
            verified_at,
        )
        reused = self._ntd.publish_provision(
            provision, structural_unit_id=UUID(str(row["structural_unit_id"]))
        )
        return NativeProvisionQualification(
            provision_id,
            1,
            verification_id,
            normative_edition_id,
            source_version_id,
            UUID(str(row["normative_artifact_id"])),
            expected_artifact_digest,
            structural_path,
            locator_ids,
            page_numbers,
            semantics.critical_tokens,
            verification_fingerprint,
            provision_fingerprint,
            reused,
        )


def _blocks_for_clause(manifest: dict[str, Any], clause_number: str) -> tuple[dict[str, Any], ...]:
    blocks = manifest.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("NTD_EXTERNAL_CANDIDATE_BLOCKS_INVALID")
    result: list[dict[str, Any]] = []
    for value in blocks:
        if not isinstance(value, dict):
            raise ValueError("NTD_EXTERNAL_CANDIDATE_BLOCK_INVALID")
        hierarchy = value.get("hierarchy")
        if isinstance(hierarchy, dict) and str(hierarchy.get("clause")) == clause_number:
            result.append(value)
    return tuple(result)


def _normalized_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _external_title_consensus(rows: Sequence[Any], designation: str) -> bool:
    expected = re.sub(r"[^0-9a-zа-я]+", "", designation.casefold().replace("ё", "е"))
    matching_receipts: set[str] = set()
    for row in rows:
        manifest = dict(row["candidate_manifest"])
        blocks = manifest.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("ambiguity_flags"):
                continue
            raw = re.sub(
                r"[^0-9a-zа-я]+",
                "",
                str(block.get("raw_transcription", "")).casefold().replace("ё", "е"),
            )
            if expected and expected in raw:
                matching_receipts.add(str(row["external_extraction_receipt_id"]))
                break
    return len(matching_receipts) >= 2


def _union_regions(blocks: tuple[dict[str, Any], ...]) -> tuple[float, float, float, float]:
    regions: list[tuple[float, float, float, float]] = []
    for block in blocks:
        value = block.get("region")
        if not isinstance(value, list) or len(value) != 4:
            raise ValueError("NTD_EXTERNAL_CANDIDATE_REGION_INVALID")
        region = tuple(float(item) for item in value)
        if not (0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1):
            raise ValueError("NTD_EXTERNAL_CANDIDATE_REGION_INVALID")
        regions.append((region[0], region[1], region[2], region[3]))
    if not regions:
        raise ValueError("NTD_EXTERNAL_CANDIDATE_REGION_MISSING")
    return (
        min(value[0] for value in regions),
        min(value[1] for value in regions),
        max(value[2] for value in regions),
        max(value[3] for value in regions),
    )


def _candidate_for_fragment(
    *,
    normative_edition_id: UUID,
    source_version_id: UUID,
    fragment: StructuralFragment,
) -> NormativeProvisionCandidate:
    first = fragment.locators[0].locator
    kind = {
        "clause": NormativeProvisionKind.CLAUSE,
        "subclause": NormativeProvisionKind.SUBCLAUSE,
        "table": NormativeProvisionKind.TABLE,
        "form": NormativeProvisionKind.FORM,
    }.get(fragment.unit_type, NormativeProvisionKind.OTHER)
    return NormativeProvisionCandidate(
        deterministic_uuid(
            f"ntd-provision-candidate:{normative_edition_id}:{fragment.structural_path}:"
            f"{fragment.fragment_digest}"
        ),
        1,
        normative_edition_id,
        source_version_id,
        fragment.structural_path,
        kind,
        first.page_number,
        first.region,
        fragment.raw_text,
        "native_pdf_layout",
        "ntd-provision-candidate-v0.1",
        fragment.fragment_digest,
        None,
    )


def _semantics_for_fragment(fragment: StructuralFragment) -> ProvisionSemantics:
    from .file_processing import derive_provision_semantics

    return derive_provision_semantics(fragment)


def remediation_environment_fingerprint(
    *, code_commit: str, lock_digest: str, python_version: str, database_version: str
) -> str:
    return digest_of(
        {
            "schema": "ntd-remediation-environment-v1",
            "code_commit": code_commit,
            "lock_digest": lock_digest,
            "python_version": python_version,
            "database_version": database_version,
        }
    )


def build_ntd_remediation_fingerprint(engine: Engine) -> dict[str, Any]:
    """Fingerprint canonical NTD remediation lineage, excluding runtime/job metadata."""

    component_queries = {
        "source_artifacts": (
            "SELECT (to_jsonb(sa)-ARRAY['created_at','correlation_id']::text[])::text "
            "FROM platform.source_artifacts sa WHERE sa.source_artifact_id IN ("
            "SELECT sv.source_artifact_id FROM platform.source_versions sv WHERE "
            "sv.source_version_id IN (SELECT source_version_id FROM platform.normative_artifacts "
            "UNION SELECT source_version_id FROM platform.ntd_seed_manifests)) "
            "ORDER BY sa.source_artifact_id"
        ),
        "source_versions": (
            "SELECT (to_jsonb(sv)-ARRAY['retrieved_at','admitted_at']::text[])::text "
            "FROM platform.source_versions sv WHERE sv.source_version_id IN ("
            "SELECT source_version_id FROM platform.normative_artifacts UNION "
            "SELECT source_version_id FROM platform.ntd_seed_manifests) "
            "ORDER BY sv.source_version_id"
        ),
        "documents": (
            "SELECT normative_document_id::text||'|'||designation_namespace||'|'||designation||'|'||"
            "issuer||'|'||jurisdiction FROM platform.normative_documents ORDER BY 1"
        ),
        "editions": (
            "SELECT normative_edition_id::text||'|'||edition_label||'|'||source_version_id::text||'|'||"
            "COALESCE(edition_fingerprint,'') FROM platform.normative_editions ORDER BY 1"
        ),
        "artifacts": (
            "SELECT normative_artifact_id::text||'|'||normative_edition_id::text||'|'||"
            "source_version_id::text||'|'||content_digest FROM platform.normative_artifacts ORDER BY 1"
        ),
        "edition_states": (
            "SELECT (to_jsonb(es)-'recorded_at')::text FROM platform.normative_edition_states es "
            "ORDER BY edition_state_id"
        ),
        "edition_relationships": (
            "SELECT relationship_fingerprint FROM platform.normative_edition_relationships "
            "ORDER BY relationship_id"
        ),
        "activation_decisions": (
            "SELECT decision_fingerprint FROM platform.normative_activation_decisions "
            "ORDER BY activation_decision_id,version"
        ),
        "applicability_decisions": (
            "SELECT decision_fingerprint FROM platform.normative_applicability_decisions "
            "ORDER BY applicability_decision_id,version"
        ),
        "applicability_predicates": (
            "SELECT semantic_fingerprint FROM platform.normative_applicability_predicates "
            "ORDER BY applicability_predicate_id,version"
        ),
        "corpus_manifests": (
            "SELECT manifest_fingerprint FROM platform.normative_corpus_manifests "
            "ORDER BY normative_corpus_manifest_id,version"
        ),
        "corpus_members": (
            "SELECT normative_corpus_manifest_id::text||'|'||manifest_version::text||'|'||"
            "corpus_member_id::text||'|'||metadata_digest FROM platform.normative_corpus_members "
            "ORDER BY normative_corpus_manifest_id,manifest_version,corpus_member_id"
        ),
        "remediation_decisions": (
            "SELECT decision_fingerprint FROM platform.ntd_seed_remediation_decisions "
            "ORDER BY remediation_decision_id,version"
        ),
        "identity_reconciliations": (
            "SELECT reconciliation_fingerprint FROM platform.ntd_seed_identity_reconciliations "
            "ORDER BY identity_reconciliation_id"
        ),
        "identity_resolutions": (
            "SELECT resolution_fingerprint FROM platform.ntd_identity_resolution_versions "
            "ORDER BY identity_resolution_id,version"
        ),
        "artifact_validations": (
            "SELECT validation_fingerprint FROM platform.normative_artifact_validations "
            "ORDER BY artifact_validation_id"
        ),
        "representation_pages": (
            "SELECT page_fingerprint FROM platform.normative_representation_pages "
            "ORDER BY normative_page_id,version"
        ),
        "structural_fragments": (
            "SELECT fragment_fingerprint FROM platform.normative_structural_fragments "
            "ORDER BY structural_fragment_id"
        ),
        "provision_candidates": (
            "SELECT provision_candidate_id::text||'|'||candidate_version::text||'|'||"
            "normative_edition_id::text||'|'||source_version_id::text||'|'||structural_path||'|'||"
            "provision_kind||'|'||content_digest FROM platform.normative_provision_candidates "
            "ORDER BY provision_candidate_id,candidate_version"
        ),
        "table_cells": (
            "SELECT cell_fingerprint FROM platform.normative_table_cells "
            "ORDER BY normative_table_cell_id"
        ),
        "references": (
            "SELECT reference_fingerprint FROM platform.normative_references "
            "ORDER BY normative_reference_id,version"
        ),
        "provision_semantics": (
            "SELECT semantics_fingerprint FROM platform.normative_provision_semantics "
            "ORDER BY provision_candidate_id,candidate_version"
        ),
        "verification_outcomes": (
            "SELECT verification_fingerprint FROM platform.normative_provision_verification_outcomes "
            "ORDER BY provision_verification_id"
        ),
        "verified_provisions": (
            "SELECT semantic_fingerprint FROM platform.normative_provision_versions "
            "ORDER BY normative_provision_id,version"
        ),
        "amendment_operations": (
            "SELECT operation_fingerprint FROM platform.normative_amendment_operations "
            "ORDER BY amendment_operation_id"
        ),
        "external_extraction": (
            "SELECT receipt_fingerprint FROM platform.ntd_external_extraction_receipts "
            "ORDER BY external_extraction_receipt_id"
        ),
        "publication_manifests": (
            "SELECT semantic_fingerprint FROM platform.ntd_publication_manifests "
            "ORDER BY publication_manifest_id"
        ),
        "acceptance_receipts": (
            "SELECT semantic_fingerprint FROM platform.ntd_document_acceptance_receipts "
            "ORDER BY document_acceptance_receipt_id"
        ),
        "practice_alignments": (
            "SELECT alignment_fingerprint FROM platform.practice_ntd_alignments "
            "ORDER BY alignment_id,version"
        ),
        "rule_evidence": (
            "SELECT rule_normative_evidence_id::text||'|'||rule_version_id::text||'|'||"
            "normative_provision_id::text||'|'||normative_provision_version::text||'|'||"
            "evidence_digest FROM platform.rule_normative_provision_evidence ORDER BY 1"
        ),
        "rule_candidates": (
            "SELECT semantic_fingerprint FROM platform.normative_rule_candidates "
            "ORDER BY normative_rule_candidate_id,version"
        ),
        "rule_qualifications": (
            "SELECT decision_fingerprint FROM platform.normative_rule_qualification_decisions "
            "ORDER BY qualification_decision_id,version"
        ),
        "rule_activation_outcomes": (
            "SELECT decision_fingerprint FROM platform.normative_rule_activation_outcomes "
            "ORDER BY rule_activation_outcome_id,version"
        ),
        "gaps": "SELECT gap_fingerprint FROM platform.ntd_gaps ORDER BY gap_fingerprint",
        "conflicts": (
            "SELECT conflict_fingerprint FROM platform.ntd_conflicts ORDER BY conflict_fingerprint"
        ),
    }
    with Session(engine) as session:
        components: dict[str, dict[str, Any]] = {}
        for name, query in component_queries.items():
            values = tuple(str(value) for value in session.execute(sa.text(query)).scalars())
            components[name] = {
                "count": len(values),
                "fingerprint": digest_of({"schema": "ntd-component-v1", "values": values}),
            }
    return {
        "schema": "ntd-remediation-memory-fingerprint-v1",
        "components": components,
        "root_fingerprint": digest_of(
            {"schema": "ntd-remediation-memory-fingerprint-v1", "components": components}
        ),
    }


def now_utc() -> datetime:
    return datetime.now(UTC)
