"""Evidence-bound ID package and template-backed generation semantics.

This module connects the existing Construction Harness requirements, WP-13
generation values and the canonical package model.  It deliberately does not
define another document-obligation model.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any
from uuid import UUID

from asd_kontur.harness.models import digest_of

from .models import FieldResolution, ResolutionState

_TOKEN = re.compile(rb"\{\{([A-Za-z0-9_.-]+)\}\}")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class RequirementState(StrEnum):
    REQUIRED = "required"
    CONDITIONAL = "conditional"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"


class MembershipState(StrEnum):
    REQUIRED = "required"
    GENERATED_CANDIDATE = "generated_candidate"
    FINALIZED = "finalized"
    COVERED = "covered"
    MISSING = "missing"
    CONFLICT = "conflict"
    INDETERMINATE = "indeterminate"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class RequirementBasis:
    source_layer: str
    source_reference: str
    exact_edition: str | None = None
    rule_version_id: UUID | None = None
    evidence_locator_ids: tuple[UUID, ...] = ()
    authority_status: str = "unresolved"

    def __post_init__(self) -> None:
        if self.source_layer not in {
            "normative",
            "project",
            "contract",
            "customer_addition",
            "methodological_practice",
        }:
            raise ValueError("unsupported requirement authority layer")
        if not self.source_reference:
            raise ValueError("requirement basis requires an exact source reference")
        if (
            self.source_layer == "normative"
            and self.exact_edition is None
            and self.authority_status != "unresolved"
        ):
            raise ValueError("resolved normative requirement basis requires an exact edition")


@dataclass(frozen=True, slots=True)
class IdDocumentRequirement:
    requirement_id: UUID
    requirement_version: int
    required_document_type_ref: str
    title: str
    state: RequirementState
    required_stage: str
    minimum_copies: int
    bases: tuple[RequirementBasis, ...]
    signer_requirements: tuple[str, ...] = ()
    required_attachment_types: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.requirement_version < 1 or self.minimum_copies < 1:
            raise ValueError("document requirement requires a positive immutable version/copies")
        if not self.bases:
            raise ValueError("document requirement cannot exist without evidence basis")
        if self.state is RequirementState.UNRESOLVED and not self.blockers:
            raise ValueError("unresolved requirement must expose a blocker")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class DocumentMembershipVersion:
    membership_id: UUID
    version: int
    role: str
    ordinal: int
    required_copy_count: int
    stage: str
    requirement_ref: tuple[UUID, int] | None
    subject_kind: str
    subject_ref: str
    state: MembershipState
    evidence_refs: tuple[str, ...]
    blocker_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 1 or self.ordinal < 1 or self.required_copy_count < 1:
            raise ValueError("membership version, ordinal and copies must be positive")
        if self.role == "register" and self.ordinal != 1:
            raise ValueError("the package register must be membership ordinal 1")
        if self.ordinal == 1 and self.role != "register":
            raise ValueError("membership ordinal 1 is reserved for the package register")
        if not self.subject_ref or not self.evidence_refs:
            raise ValueError("membership requires an exact subject and provenance")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class VolumeBookVersion:
    volume_book_id: UUID
    version: int
    title: str
    ordinal: int
    register_level: str
    required_copy_count: int
    memberships: tuple[DocumentMembershipVersion, ...]

    def __post_init__(self) -> None:
        if self.version < 1 or self.ordinal < 1 or self.required_copy_count < 1:
            raise ValueError("volume/book version, ordinal and copies must be positive")
        ordinals = tuple(item.ordinal for item in self.memberships)
        if not ordinals or ordinals[0] != 1 or len(ordinals) != len(set(ordinals)):
            raise ValueError("book memberships require unique ordinals beginning with register")
        if tuple(sorted(ordinals)) != ordinals:
            raise ValueError("book memberships must be ordered")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class IdPackageVersion:
    package_id: UUID
    version: int
    work_package_ref: tuple[UUID, int]
    matrix_ref: tuple[UUID, int]
    rule_set_version_id: UUID | None
    purpose: str
    books: tuple[VolumeBookVersion, ...]
    governance_blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 1 or not self.books:
            raise ValueError("ID package requires an immutable version and at least one book")
        if (
            self.rule_set_version_id is None
            and "RULE_SET_VERSION_UNRESOLVED" not in self.governance_blockers
        ):
            raise ValueError("package without a RuleSet must expose the governance blocker")
        if len({book.ordinal for book in self.books}) != len(self.books):
            raise ValueError("volume/book ordinals must be unique")

    @property
    def fingerprint(self) -> str:
        return digest_of(self)


@dataclass(frozen=True, slots=True)
class PackageReadinessEvaluation:
    package_ref: tuple[UUID, int]
    required: int
    covered: int
    generated_candidates: int
    finalized: int
    missing: int
    conflicts: int
    indeterminate: int
    blocked: int
    not_applicable: int
    blocker_codes: tuple[str, ...]
    status: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            min(
                self.required,
                self.covered,
                self.generated_candidates,
                self.finalized,
                self.missing,
                self.conflicts,
                self.indeterminate,
                self.blocked,
                self.not_applicable,
            )
            < 0
        ):
            raise ValueError("readiness denominators cannot be negative")
        object.__setattr__(self, "fingerprint", digest_of(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "package_ref": self.package_ref,
            "required": self.required,
            "covered": self.covered,
            "generated_candidates": self.generated_candidates,
            "finalized": self.finalized,
            "missing": self.missing,
            "conflicts": self.conflicts,
            "indeterminate": self.indeterminate,
            "blocked": self.blocked,
            "not_applicable": self.not_applicable,
            "blocker_codes": self.blocker_codes,
            "status": self.status,
        }


def evaluate_package_readiness(package: IdPackageVersion) -> PackageReadinessEvaluation:
    memberships = tuple(member for book in package.books for member in book.memberships)
    document_memberships = tuple(member for member in memberships if member.role != "register")
    counts = {state: 0 for state in MembershipState}
    blockers: set[str] = set()
    blockers.update(package.governance_blockers)
    for member in memberships:
        blockers.update(member.blocker_codes)
    for member in document_memberships:
        counts[member.state] += 1
    required = len(
        [item for item in document_memberships if item.state is not MembershipState.NOT_APPLICABLE]
    )
    incomplete = (
        counts[MembershipState.MISSING]
        + counts[MembershipState.CONFLICT]
        + counts[MembershipState.INDETERMINATE]
        + counts[MembershipState.BLOCKED]
        + counts[MembershipState.REQUIRED]
        + counts[MembershipState.GENERATED_CANDIDATE]
    )
    status = "ready" if incomplete == 0 and not blockers else "incomplete"
    return PackageReadinessEvaluation(
        (package.package_id, package.version),
        required,
        counts[MembershipState.COVERED],
        counts[MembershipState.GENERATED_CANDIDATE],
        counts[MembershipState.FINALIZED],
        counts[MembershipState.MISSING],
        counts[MembershipState.CONFLICT],
        counts[MembershipState.INDETERMINATE],
        counts[MembershipState.BLOCKED],
        counts[MembershipState.NOT_APPLICABLE],
        tuple(sorted(blockers)),
        status,
    )


@dataclass(frozen=True, slots=True)
class MembershipRevision:
    membership_id: UUID
    subject_kind: str | None = None
    subject_ref: str | None = None
    state: MembershipState | None = None
    required_copy_count: int | None = None
    stage: str | None = None
    evidence_refs: tuple[str, ...] = ()
    blocker_codes: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.required_copy_count is not None and self.required_copy_count < 1:
            raise ValueError("membership revision copies must be positive")
        if (self.subject_kind is None) != (self.subject_ref is None):
            raise ValueError("membership subject kind and ref must change together")


def evolve_package_version(
    package: IdPackageVersion,
    *,
    revisions: tuple[MembershipRevision, ...] = (),
    removed_membership_ids: tuple[UUID, ...] = (),
    body_order: tuple[UUID, ...] | None = None,
) -> IdPackageVersion:
    """Create a new immutable package/book/membership version and register basis.

    Register content is always derived later from the returned exact version;
    callers cannot supply an independent register manifest.
    """

    revision_map = {item.membership_id: item for item in revisions}
    if len(revision_map) != len(revisions):
        raise ValueError("duplicate membership revisions are forbidden")
    removed = set(removed_membership_ids)
    existing_ids = {member.membership_id for book in package.books for member in book.memberships}
    if not set(revision_map).issubset(existing_ids) or not removed.issubset(existing_ids):
        raise ValueError("membership revision references an unknown package member")
    if any(
        member.role == "register" and member.membership_id in removed
        for book in package.books
        for member in book.memberships
    ):
        raise ValueError("package register cannot be removed")
    new_package_version = package.version + 1
    books: list[VolumeBookVersion] = []
    for book in package.books:
        register = book.memberships[0]
        body = [item for item in book.memberships[1:] if item.membership_id not in removed]
        if body_order is not None:
            if set(body_order) != {item.membership_id for item in body}:
                raise ValueError(
                    "body order must contain every retained non-register membership once"
                )
            index = {item.membership_id: item for item in body}
            body = [index[identity] for identity in body_order]
        revised: list[DocumentMembershipVersion] = [
            replace(
                register,
                version=register.version + 1,
                subject_ref=f"package-register:{package.package_id}:v{new_package_version}",
                evidence_refs=(
                    *register.evidence_refs,
                    f"package-version:{package.package_id}:v{new_package_version}",
                ),
            )
        ]
        for ordinal, member in enumerate(body, start=2):
            change = revision_map.get(member.membership_id)
            evidence = member.evidence_refs
            if change is not None:
                evidence = (*evidence, *change.evidence_refs)
            revised.append(
                replace(
                    member,
                    version=member.version + 1,
                    ordinal=ordinal,
                    subject_kind=(
                        change.subject_kind
                        if change is not None and change.subject_kind is not None
                        else member.subject_kind
                    ),
                    subject_ref=(
                        change.subject_ref
                        if change is not None and change.subject_ref is not None
                        else member.subject_ref
                    ),
                    state=(change.state if change is not None and change.state else member.state),
                    required_copy_count=(
                        change.required_copy_count
                        if change is not None and change.required_copy_count is not None
                        else member.required_copy_count
                    ),
                    stage=(
                        change.stage
                        if change is not None and change.stage is not None
                        else member.stage
                    ),
                    evidence_refs=evidence,
                    blocker_codes=(
                        change.blocker_codes
                        if change is not None and change.blocker_codes is not None
                        else member.blocker_codes
                    ),
                )
            )
        books.append(replace(book, version=book.version + 1, memberships=tuple(revised)))
    return replace(package, version=new_package_version, books=tuple(books))


def registry_manifest(package: IdPackageVersion, book: VolumeBookVersion) -> dict[str, Any]:
    if book not in package.books:
        raise ValueError("registry book does not belong to package version")
    register = book.memberships[0]
    if register.role != "register" or register.ordinal != 1:
        raise ValueError("registry membership invariant violated")
    listed = [
        {
            "ordinal": item.ordinal,
            "membership_id": str(item.membership_id),
            "membership_version": item.version,
            "role": item.role,
            "subject_kind": item.subject_kind,
            "subject_ref": item.subject_ref,
            "copies": item.required_copy_count,
            "stage": item.stage,
            "state": item.state,
        }
        for item in book.memberships[1:]
    ]
    return {
        "package_id": str(package.package_id),
        "package_version": package.version,
        "volume_book_id": str(book.volume_book_id),
        "volume_book_version": book.version,
        "register_membership_id": str(register.membership_id),
        "documents": listed,
        "fingerprint": digest_of(listed),
    }


@dataclass(frozen=True, slots=True)
class TemplateRenderResult:
    package_bytes: bytes = field(repr=False, compare=False)
    bytes_digest: str
    semantic_fingerprint: str
    structural_checks: tuple[str, ...]


class TemplateBackedDocxRenderer:
    """Stateless renderer over exact immutable DOCX TemplateVersion bytes."""

    profile_version = "support.template-docx-renderer@1.0.0"

    def render(
        self,
        *,
        template_bytes: bytes,
        template_digest: str,
        fields: tuple[FieldResolution, ...],
        semantic_input: dict[str, Any],
    ) -> TemplateRenderResult:
        observed = "sha256:" + hashlib.sha256(template_bytes).hexdigest()
        if observed != template_digest:
            raise ValueError("template_bytes_digest_mismatch")
        blocked = [
            item.field_key
            for item in fields
            if item.material
            and item.state not in {ResolutionState.CONFIRMED, ResolutionState.NOT_APPLICABLE}
        ]
        if blocked:
            raise ValueError("generation_material_fields_unresolved:" + ",".join(sorted(blocked)))
        values = {
            item.field_key: (item.display_value or str(item.normalized_value or ""))
            for item in fields
            if item.state is ResolutionState.CONFIRMED
        }
        source = io.BytesIO(template_bytes)
        target = io.BytesIO()
        found: set[str] = set()
        with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, "w") as outgoing:
            names = incoming.namelist()
            if "word/document.xml" not in names:
                raise ValueError("template_docx_main_document_missing")
            if any(name.endswith("vbaProject.bin") or "externalLink" in name for name in names):
                raise ValueError("template_active_or_external_content_forbidden")
            for name in sorted(names):
                payload = incoming.read(name)
                if name.startswith("word/") and name.endswith(".xml"):

                    def replace(match: re.Match[bytes]) -> bytes:
                        key = match.group(1).decode("ascii")
                        found.add(key)
                        if key not in values:
                            return match.group(0)
                        return _xml_bytes(values[key])

                    payload = _TOKEN.sub(replace, payload)
                info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                outgoing.writestr(info, payload)
        missing_bindings = sorted(set(values) - found)
        unresolved = sorted(found - set(values))
        if missing_bindings or unresolved:
            reasons = [
                *(f"binding_missing:{item}" for item in missing_bindings),
                *(f"field_unresolved:{item}" for item in unresolved),
            ]
            raise ValueError("template_binding_validation_failed:" + ",".join(reasons))
        result = target.getvalue()
        return TemplateRenderResult(
            result,
            "sha256:" + hashlib.sha256(result).hexdigest(),
            digest_of(
                {
                    "template_digest": template_digest,
                    "renderer_profile": self.profile_version,
                    "fields": fields,
                    "semantic_input": semantic_input,
                }
            ),
            (
                "TEMPLATE_DIGEST_VERIFIED",
                "DOCX_PACKAGE_OPENED",
                "ACTIVE_CONTENT_ABSENT",
                "FIELD_BINDINGS_COMPLETE",
                "FRESH_DOCUMENT_INSTANCE",
            ),
        )


def _xml_bytes(value: str) -> bytes:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").encode("utf-8")
