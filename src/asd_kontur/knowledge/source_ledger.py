"""Narrow platform Source/Evidence Ledger application service."""

# ruff: noqa: E501 -- SQL fragments retain readable clause boundaries.

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .errors import KnowledgeError, KnowledgeErrorCode
from .object_store import ObjectStorePort


def _digest(value: str | bytes) -> str:
    data = value.encode() if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


@dataclass(frozen=True, slots=True)
class OfficialSourceRegistration:
    source_family_key: str
    official_url: str
    issuer: str
    jurisdiction: str
    metadata: str
    actor_identity_id: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class PlatformSourceAdmission:
    source_family_key: str
    stable_designation: str
    title: str
    issuer: str
    jurisdiction: str
    external_version_label: str
    source_kind: str
    locator: str
    acquisition_method: str
    semantic_metadata: str
    media_type: str
    classification: str
    retention_class: str
    actor_identity_id: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class AdmittedSourceVersion:
    source_artifact_id: UUID
    source_version_id: UUID
    content_digest: str
    duplicate: bool


class PlatformSourceLedger:
    """Curator-only platform ledger; object persistence precedes domain acceptance."""

    def __init__(self, engine: Engine, object_store: ObjectStorePort) -> None:
        self._engine = engine
        self._objects = object_store

    def register_official_source(self, registration: OfficialSourceRegistration) -> UUID:
        registry_id = uuid7()
        with Session(self._engine) as session, session.begin():
            existing = (
                session.execute(
                    sa.text(
                        "SELECT registry_entry_id, official_url, registry_metadata_digest "
                        "FROM platform.official_source_registry_entries "
                        "WHERE source_family_key=:family"
                    ),
                    {"family": registration.source_family_key},
                )
                .mappings()
                .one_or_none()
            )
            metadata_digest = _digest(registration.metadata)
            if existing is not None:
                if (
                    existing["official_url"] != registration.official_url
                    or existing["registry_metadata_digest"] != metadata_digest
                ):
                    raise KnowledgeError(
                        KnowledgeErrorCode.LOCATOR_CONFLICT,
                        "Official source metadata changed and requires an explicit new registry revision.",
                    )
                return UUID(str(existing["registry_entry_id"]))
            session.execute(
                sa.text(
                    "INSERT INTO platform.official_source_registry_entries "
                    "(registry_entry_id,source_family_key,official_url,issuer,jurisdiction,"
                    "registry_metadata_digest,status,created_by_identity_id,correlation_id,observed_at) "
                    "VALUES (:id,:family,:url,:issuer,:jurisdiction,:digest,'registered',:actor,:correlation,:now)"
                ),
                {
                    "id": registry_id,
                    "family": registration.source_family_key,
                    "url": registration.official_url,
                    "issuer": registration.issuer,
                    "jurisdiction": registration.jurisdiction,
                    "digest": metadata_digest,
                    "actor": registration.actor_identity_id,
                    "correlation": registration.correlation_id,
                    "now": datetime.now(UTC),
                },
            )
        return registry_id

    def admit(self, request: PlatformSourceAdmission, content: bytes) -> AdmittedSourceVersion:
        artifact_id, attempt_id = self._begin_attempt(request)
        content_digest = _digest(content)
        with Session(self._engine) as session:
            duplicate = session.execute(
                sa.text(
                    "SELECT source_version_id FROM platform.source_versions "
                    "WHERE source_artifact_id=:artifact AND content_digest=:digest"
                ),
                {"artifact": artifact_id, "digest": content_digest},
            ).scalar_one_or_none()
        if duplicate is not None:
            with Session(self._engine) as session, session.begin():
                session.execute(
                    sa.text(
                        "UPDATE platform.acquisition_attempts SET status='accepted',retrieved_at=:now,"
                        "observed_content_digest=:digest WHERE acquisition_attempt_id=:id"
                    ),
                    {"id": attempt_id, "now": datetime.now(UTC), "digest": content_digest},
                )
            return AdmittedSourceVersion(artifact_id, UUID(str(duplicate)), content_digest, True)
        object_id = uuid7()
        object_key = f"platform/source/{object_id}"
        operation_id = str(attempt_id)
        try:
            receipt = self._objects.put_immutable(
                operation_id=operation_id, object_key=object_key, content=content
            )
        except KnowledgeError as error:
            self._finish_failed_attempt(attempt_id, error.code)
            raise
        try:
            return self._accept(request, artifact_id, attempt_id, object_id, receipt)
        except (IntegrityError, KnowledgeError) as error:
            removed = self._objects.delete(object_key)
            code = (
                KnowledgeErrorCode.VERSION_CONFLICT
                if removed
                else KnowledgeErrorCode.RECONCILIATION_REQUIRED
            )
            self._finish_failed_attempt(attempt_id, code)
            if isinstance(error, KnowledgeError):
                raise
            raise KnowledgeError(
                code, "Source version conflicts with an immutable ledger entry."
            ) from error

    def _begin_attempt(self, request: PlatformSourceAdmission) -> tuple[UUID, UUID]:
        artifact_id = uuid7()
        attempt_id = uuid7()
        with Session(self._engine) as session, session.begin():
            registry_id = session.execute(
                sa.text(
                    "SELECT registry_entry_id FROM platform.official_source_registry_entries "
                    "WHERE source_family_key=:family AND status='registered'"
                ),
                {"family": request.source_family_key},
            ).scalar_one()
            existing = session.execute(
                sa.text(
                    "SELECT source_artifact_id FROM platform.source_artifacts "
                    "WHERE issuer=:issuer AND jurisdiction=:jurisdiction AND stable_designation=:designation"
                ),
                {
                    "issuer": request.issuer,
                    "jurisdiction": request.jurisdiction,
                    "designation": request.stable_designation,
                },
            ).scalar_one_or_none()
            if existing is None:
                session.execute(
                    sa.text(
                        "INSERT INTO platform.source_artifacts "
                        "(source_artifact_id,source_kind,title,issuer,jurisdiction,stable_designation,"
                        "status,retention_class,created_by_identity_id,correlation_id) "
                        "VALUES (:id,:kind,:title,:issuer,:jurisdiction,:designation,'active',:retention,:actor,:correlation)"
                    ),
                    {
                        "id": artifact_id,
                        "kind": request.source_kind,
                        "title": request.title,
                        "issuer": request.issuer,
                        "jurisdiction": request.jurisdiction,
                        "designation": request.stable_designation,
                        "retention": request.retention_class,
                        "actor": request.actor_identity_id,
                        "correlation": request.correlation_id,
                    },
                )
            else:
                artifact_id = UUID(str(existing))
            session.execute(
                sa.text(
                    "INSERT INTO platform.acquisition_attempts "
                    "(acquisition_attempt_id,registry_entry_id,source_artifact_id,acquisition_method,"
                    "external_locator,requested_at,status,correlation_id) "
                    "VALUES (:id,:registry,:artifact,:method,:locator,:now,'started',:correlation)"
                ),
                {
                    "id": attempt_id,
                    "registry": registry_id,
                    "artifact": artifact_id,
                    "method": request.acquisition_method,
                    "locator": request.locator,
                    "now": datetime.now(UTC),
                    "correlation": request.correlation_id,
                },
            )
        return artifact_id, attempt_id

    def _accept(
        self,
        request: PlatformSourceAdmission,
        artifact_id: UUID,
        attempt_id: UUID,
        object_id: UUID,
        receipt: object,
    ) -> AdmittedSourceVersion:
        from .object_store import ObjectWriteReceipt

        assert isinstance(receipt, ObjectWriteReceipt)
        with Session(self._engine) as session, session.begin():
            ordinal = session.execute(
                sa.text(
                    "SELECT COALESCE(max(version_ordinal),0)+1 FROM platform.source_versions "
                    "WHERE source_artifact_id=:artifact"
                ),
                {"artifact": artifact_id},
            ).scalar_one()
            version_id, object_receipt_id, locator_id = uuid7(), uuid7(), uuid7()
            now = datetime.now(UTC)
            session.execute(
                sa.text(
                    "INSERT INTO platform.objects "
                    "(object_id,object_version,content_digest,size_bytes,media_type,storage_adapter_key,"
                    "access_capability_ref,classification,retention_class,created_by_identity_id,correlation_id) "
                    "VALUES (:id,1,:digest,:size,:media,'test-port',:capability,:classification,:retention,:actor,:correlation)"
                ),
                {
                    "id": object_id,
                    "digest": receipt.digest,
                    "size": receipt.size_bytes,
                    "media": request.media_type,
                    "capability": f"object-capability:{object_id}",
                    "classification": request.classification,
                    "retention": request.retention_class,
                    "actor": request.actor_identity_id,
                    "correlation": request.correlation_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.object_receipts "
                    "(object_receipt_id,object_id,object_version,adapter_key,operation_id,status,"
                    "observed_digest,observed_size_bytes,residue_state) "
                    "VALUES (:receipt,:object,1,'test-port',:operation,'verified',:digest,:size,'none')"
                ),
                {
                    "receipt": object_receipt_id,
                    "object": object_id,
                    "operation": receipt.operation_id,
                    "digest": receipt.digest,
                    "size": receipt.size_bytes,
                },
            )
            session.execute(
                sa.text(
                    "UPDATE platform.acquisition_attempts SET status='bytes_written',retrieved_at=:now,"
                    "observed_content_digest=:digest,object_receipt_id=:receipt "
                    "WHERE acquisition_attempt_id=:attempt"
                ),
                {
                    "now": now,
                    "digest": receipt.digest,
                    "receipt": object_receipt_id,
                    "attempt": attempt_id,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.source_versions "
                    "(source_version_id,source_artifact_id,version_ordinal,external_version_label,"
                    "object_id,object_version,object_receipt_id,acquisition_attempt_id,content_digest,semantic_metadata_digest,"
                    "acquisition_method,retrieved_at,admission_status,admitted_by_identity_id,retention_class) "
                    "VALUES (:version,:artifact,:ordinal,:label,:object,1,:receipt,:attempt,:digest,:metadata,"
                    ":method,:now,'accepted',:actor,:retention)"
                ),
                {
                    "version": version_id,
                    "artifact": artifact_id,
                    "ordinal": ordinal,
                    "label": request.external_version_label,
                    "object": object_id,
                    "receipt": object_receipt_id,
                    "attempt": attempt_id,
                    "digest": receipt.digest,
                    "metadata": _digest(request.semantic_metadata),
                    "method": request.acquisition_method,
                    "now": now,
                    "actor": request.actor_identity_id,
                    "retention": request.retention_class,
                },
            )
            session.execute(
                sa.text(
                    "INSERT INTO platform.source_locators "
                    "(source_locator_id,source_version_id,locator_kind,locator_key,locator_value) "
                    "VALUES (:id,:version,'official_url','document',CAST(:locator AS jsonb))"
                ),
                {
                    "id": locator_id,
                    "version": version_id,
                    "locator": json.dumps({"url": request.locator}),
                },
            )
            session.execute(
                sa.text(
                    "UPDATE platform.acquisition_attempts SET status='accepted' "
                    "WHERE acquisition_attempt_id=:attempt"
                ),
                {"attempt": attempt_id},
            )
        return AdmittedSourceVersion(artifact_id, version_id, receipt.digest, False)

    def _finish_failed_attempt(self, attempt_id: UUID, code: KnowledgeErrorCode) -> None:
        status = (
            "reconciliation_required"
            if code is KnowledgeErrorCode.RECONCILIATION_REQUIRED
            else "failed"
        )
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "UPDATE platform.acquisition_attempts SET status=:status,error_code=:code "
                    "WHERE acquisition_attempt_id=:id"
                ),
                {"status": status, "code": code, "id": attempt_id},
            )
