"""Planning, authorization, exact purge, residual verification and attestation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from asd_kontur.domain import uuid7

from .errors import LifecycleError, LifecycleErrorCode
from .models import (
    AdapterOutcome,
    AdapterReceipt,
    AssuranceClass,
    Authority,
    Basis,
    DeletionItem,
    DeletionPlan,
    DestructionAttestation,
    DestructiveAuthorization,
    ExactVersionReference,
    InventoryItem,
    RecoveryCheckpoint,
    ResidualScan,
    RetentionProfile,
    VerificationOutcome,
)
from .storage import StorageAdapter, inventory_digest

RESET_CAPABILITY: Final = "workspace.reset.authorize"
DESTROY_CAPABILITY: Final = "workspace.destroy.authorize"
RESET_EXECUTE_CAPABILITY: Final = "workspace.purge.execute"
DESTROY_EXECUTE_CAPABILITY: Final = "workspace.destroy.execute"
RESET_VERIFY_CAPABILITY: Final = "workspace.reset.verify"
DESTROY_VERIFY_CAPABILITY: Final = "workspace.destroy.verify"


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    reference: ExactVersionReference
    adapters: tuple[StorageAdapter, ...]

    def by_key(self) -> dict[str, StorageAdapter]:
        result = {adapter.definition.adapter_key: adapter for adapter in self.adapters}
        if len(result) != len(self.adapters):
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "Storage Adapter Registry contains duplicate adapter keys.",
            )
        return result


@dataclass(frozen=True, slots=True)
class PurgeOutcome:
    operation_id: UUID
    receipts: tuple[AdapterReceipt, ...]
    complete: bool


class DestructionCoordinator:
    """Fail-closed coordinator; adapters execute only an immutable exact plan."""

    def __init__(self, registry: RegistrySnapshot) -> None:
        self._registry = registry

    def plan(
        self,
        *,
        operation_kind: str,
        organization_id: UUID,
        workspace_id: UUID,
        lifecycle_version: int,
        workspace_revision: int,
        profile: RetentionProfile,
        basis: Basis,
        requester: Authority,
        legal_hold_active: bool,
        now: datetime,
        expires_at: datetime,
    ) -> DeletionPlan:
        if operation_kind not in {"reset", "destroy"}:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "The destructive operation kind must be reset or destroy.",
            )
        required_capability = (
            "workspace.reset.plan" if operation_kind == "reset" else "workspace.destroy.plan"
        )
        if required_capability not in requester.capabilities:
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                f"Capability {required_capability} is required.",
            )
        if legal_hold_active:
            raise LifecycleError(
                LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                "A current legal hold blocks destructive planning.",
            )
        if not profile.complete:
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "The RetentionProfile is incomplete.",
            )
        if profile.environment == "production" and not profile.production_approved:
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "Production retention values are not approved.",
            )
        if not basis.evidence_refs or basis.effective_until <= now:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "The Basis Registry entry is missing evidence or has expired.",
            )
        inventories = self._inventory(workspace_id)
        retained = profile.retained_on_reset if operation_kind == "reset" else frozenset()
        unknown_retained = retained - frozenset(inventories)
        if unknown_retained:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "RetentionProfile refers to an adapter outside the exact registry snapshot.",
            )
        items = tuple(
            DeletionItem(adapter_key, item_id, operation_kind)
            for adapter_key, inventory in sorted(inventories.items())
            if adapter_key not in retained
            for item_id in (tuple(item.item_id for item in inventory) or ("__inventory_empty__",))
        )
        return DeletionPlan(
            uuid7(),
            1,
            operation_kind,
            organization_id,
            workspace_id,
            lifecycle_version,
            workspace_revision,
            profile.reference,
            basis,
            now,
            inventory_digest(inventories),
            self._registry.reference,
            items,
            tuple(sorted(retained)),
            requester.identity_id,
            True,
            expires_at,
        )

    def authorize(
        self,
        *,
        plan: DeletionPlan,
        requester: Authority,
        confirmer: Authority,
        executor: Authority,
        verifier: Authority,
        current_lifecycle_version: int,
        legal_hold_active: bool,
        now: datetime,
    ) -> DestructiveAuthorization:
        capability = RESET_CAPABILITY if plan.operation_kind == "reset" else DESTROY_CAPABILITY
        executor_capability = (
            RESET_EXECUTE_CAPABILITY
            if plan.operation_kind == "reset"
            else DESTROY_EXECUTE_CAPABILITY
        )
        verifier_capability = (
            RESET_VERIFY_CAPABILITY if plan.operation_kind == "reset" else DESTROY_VERIFY_CAPABILITY
        )
        if (
            not requester.is_human
            or requester.identity_id != plan.requester_identity_id
            or not confirmer.is_human
            or capability not in confirmer.capabilities
        ):
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                "A qualified human requester and independent confirmer are required.",
            )
        identities = {
            requester.identity_id,
            confirmer.identity_id,
            executor.identity_id,
            verifier.identity_id,
        }
        if (
            len(identities) != 4
            or executor.is_human
            or executor_capability not in executor.capabilities
            or not verifier.is_human
        ):
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                "Requester, confirmer, service executor, and human verifier must be independent.",
            )
        if verifier_capability not in verifier.capabilities:
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                "The independent verifier lacks the required capability.",
            )
        if legal_hold_active:
            raise LifecycleError(
                LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                "A current legal hold invalidates destructive authorization.",
            )
        if plan.expires_at <= now or current_lifecycle_version != plan.lifecycle_version:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "The plan is expired or its lifecycle version is stale.",
            )
        if inventory_digest(self._inventory(plan.workspace_id)) != plan.inventory_digest:
            raise LifecycleError(
                LifecycleErrorCode.INVENTORY_CHANGED,
                "Workspace inventory changed after the dry-run plan.",
            )
        return DestructiveAuthorization(
            uuid7(),
            plan.plan_id,
            plan.digest,
            requester.identity_id,
            confirmer.identity_id,
            executor.identity_id,
            verifier.identity_id,
            now,
            plan.expires_at,
        )

    def assert_plan_current(
        self,
        *,
        plan: DeletionPlan,
        current_lifecycle_version: int,
        legal_hold_active: bool,
        now: datetime,
    ) -> None:
        if legal_hold_active:
            raise LifecycleError(
                LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                "A current legal hold invalidates the destructive plan.",
            )
        if plan.expires_at <= now or current_lifecycle_version < plan.lifecycle_version:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "The destructive plan is expired or ahead of lifecycle state.",
            )
        if inventory_digest(self._inventory(plan.workspace_id)) != plan.inventory_digest:
            raise LifecycleError(
                LifecycleErrorCode.INVENTORY_CHANGED,
                "Workspace inventory changed after destructive authorization.",
            )

    def execute(
        self,
        *,
        plan: DeletionPlan,
        authorization: DestructiveAuthorization,
        executor: Authority,
        legal_hold_active: bool,
        now: datetime,
        operation_id: UUID | None = None,
    ) -> PurgeOutcome:
        if (
            authorization.plan_id != plan.plan_id
            or authorization.plan_digest != plan.digest
            or authorization.executor_identity_id != executor.identity_id
            or authorization.expires_at <= now
        ):
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                "Execution is not bound to the current immutable plan and authority.",
            )
        if legal_hold_active:
            raise LifecycleError(
                LifecycleErrorCode.LEGAL_HOLD_ACTIVE,
                "A current legal hold stops destructive execution at a safe checkpoint.",
            )
        adapters = self._registry.by_key()
        operation_id = operation_id or uuid7()
        receipts: list[AdapterReceipt] = []
        for item in plan.items:
            adapter = adapters.get(item.adapter_key)
            adapter_capable = adapter is not None and (
                adapter.definition.purge_capable
                if plan.operation_kind == "reset"
                else adapter.definition.destroy_capable
            )
            if not adapter_capable:
                receipts.append(
                    AdapterReceipt(
                        uuid7(),
                        item.adapter_key,
                        item.item_id,
                        AdapterOutcome.INCOMPLETE,
                        1,
                        1,
                        operation_id,
                        now,
                    )
                )
                continue
            assert adapter is not None
            receipts.append(
                adapter.purge_item(
                    workspace_id=plan.workspace_id,
                    item_id=item.item_id,
                    operation_id=operation_id,
                )
            )
        complete = all(
            receipt.outcome in {AdapterOutcome.DELETED, AdapterOutcome.ALREADY_ABSENT}
            for receipt in receipts
        )
        return PurgeOutcome(operation_id, tuple(receipts), complete)

    def verify(
        self,
        *,
        plan: DeletionPlan,
        known_ids: frozenset[str],
        known_digests: frozenset[str],
        known_fragments: frozenset[str],
        now: datetime,
    ) -> tuple[ResidualScan, ...]:
        scans: list[ResidualScan] = []
        for adapter in self._registry.adapters:
            definition = adapter.definition
            if definition.health != "available" or not definition.residue_verification_capable:
                scans.append(
                    ResidualScan(
                        uuid7(),
                        definition.adapter_key,
                        ("workspace_id", "composite_scope"),
                        VerificationOutcome.INCOMPLETE,
                        0,
                        0,
                        (),
                        now,
                    )
                )
                continue
            findings = adapter.find_residue(
                workspace_id=plan.workspace_id,
                known_ids=known_ids,
                known_digests=known_digests,
                known_fragments=known_fragments,
            )
            foreign = sum(item.workspace_id != plan.workspace_id for item in findings)
            allowed = definition.adapter_key in plan.expected_residue_classes
            outcome = (
                VerificationOutcome.QUARANTINED
                if foreign
                else VerificationOutcome.VERIFIED
                if allowed
                else VerificationOutcome.FAILED
                if findings
                else VerificationOutcome.VERIFIED
            )
            scans.append(
                ResidualScan(
                    uuid7(),
                    definition.adapter_key,
                    (
                        "workspace_id",
                        "organization_workspace_scope",
                        "known_id",
                        "known_digest",
                        "known_fragment",
                    ),
                    outcome,
                    len(findings),
                    foreign,
                    (definition.adapter_key,) if allowed and findings else (),
                    now,
                )
            )
        return tuple(scans)

    @staticmethod
    def checkpoint(
        *,
        plan: DeletionPlan,
        outcome: PurgeOutcome,
        now: datetime,
    ) -> RecoveryCheckpoint:
        if outcome.complete:
            raise LifecycleError(
                LifecycleErrorCode.PLAN_INVALID,
                "A completed destructive operation does not require recovery.",
            )
        pending = tuple(
            f"{receipt.adapter_key}:{receipt.item_id}"
            for receipt in outcome.receipts
            if receipt.outcome not in {AdapterOutcome.DELETED, AdapterOutcome.ALREADY_ABSENT}
        )
        completed = tuple(
            f"{receipt.adapter_key}:{receipt.item_id}"
            for receipt in outcome.receipts
            if receipt.outcome in {AdapterOutcome.DELETED, AdapterOutcome.ALREADY_ABSENT}
        )
        return RecoveryCheckpoint(
            uuid7(),
            outcome.operation_id,
            plan.digest,
            plan.operation_kind,
            tuple(
                sorted(
                    {
                        receipt.adapter_key
                        for receipt in outcome.receipts
                        if receipt.outcome
                        not in {AdapterOutcome.DELETED, AdapterOutcome.ALREADY_ABSENT}
                    }
                )
            ),
            completed,
            pending,
            now,
        )

    def attest(
        self,
        *,
        plan: DeletionPlan,
        authorization: DestructiveAuthorization,
        receipts: tuple[AdapterReceipt, ...],
        scans: tuple[ResidualScan, ...],
        profile: RetentionProfile,
        platform_integrity_before: str,
        platform_integrity_after: str,
        legal_hold_check_ids: tuple[UUID, ...],
        verifier: Authority,
        now: datetime,
        requested_assurance: AssuranceClass,
    ) -> DestructionAttestation:
        if authorization.verifier_identity_id != verifier.identity_id or not verifier.is_human:
            raise LifecycleError(
                LifecycleErrorCode.AUTHORITY_DENIED,
                "Only the bound independent human verifier may attest.",
            )
        if requested_assurance is AssuranceClass.PRODUCTION and (
            profile.environment != "production" or not profile.production_approved
        ):
            raise LifecycleError(
                LifecycleErrorCode.POLICY_BLOCKED,
                "Development evidence cannot create a production attestation.",
            )
        required_scan_keys = {
            adapter.definition.adapter_key
            for adapter in self._registry.adapters
            if adapter.definition.required
        }
        required_receipt_keys = {item.adapter_key for item in plan.items}
        scan_keys = {scan.adapter_key for scan in scans}
        receipt_keys = {receipt.adapter_key for receipt in receipts}
        any_quarantine = any(scan.outcome is VerificationOutcome.QUARANTINED for scan in scans)
        all_scans_verified = all(scan.outcome is VerificationOutcome.VERIFIED for scan in scans)
        all_receipts_terminal = all(
            receipt.outcome in {AdapterOutcome.DELETED, AdapterOutcome.ALREADY_ABSENT}
            for receipt in receipts
        )
        if any_quarantine:
            outcome = VerificationOutcome.QUARANTINED
        elif (
            required_scan_keys <= scan_keys
            and required_receipt_keys <= receipt_keys
            and all_scans_verified
            and all_receipts_terminal
            and platform_integrity_before == platform_integrity_after
        ):
            outcome = VerificationOutcome.VERIFIED
        else:
            outcome = VerificationOutcome.INCOMPLETE
        return DestructionAttestation(
            uuid7(),
            1,
            plan.workspace_id,
            plan.workspace_revision,
            plan.plan_id,
            plan.digest,
            profile.reference,
            plan.basis.registry,
            plan.basis.code,
            legal_hold_check_ids,
            authorization.requester_identity_id,
            authorization.confirmer_identity_id,
            authorization.executor_identity_id,
            authorization.verifier_identity_id,
            self._registry.reference,
            tuple(receipt.receipt_id for receipt in receipts),
            tuple(scan.scan_id for scan in scans),
            sum(receipt.before_count - receipt.after_count for receipt in receipts),
            sum(scan.found_count for scan in scans if not scan.allowed_residue_classes),
            tuple(sorted({item for scan in scans for item in scan.allowed_residue_classes})),
            platform_integrity_before,
            platform_integrity_after,
            now,
            requested_assurance,
            outcome,
        )

    def _inventory(self, workspace_id: UUID) -> dict[str, tuple[InventoryItem, ...]]:
        inventories: dict[str, tuple[InventoryItem, ...]] = {}
        for adapter in self._registry.adapters:
            definition = adapter.definition
            if definition.required and (
                definition.health != "available" or not definition.inventory_capable
            ):
                raise LifecycleError(
                    LifecycleErrorCode.ADAPTER_UNAVAILABLE,
                    f"Required adapter {definition.adapter_key} cannot be inventoried.",
                )
            inventories[definition.adapter_key] = adapter.inventory(workspace_id)
        return inventories
