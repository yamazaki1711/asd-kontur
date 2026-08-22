"""Workspace-scoped at-least-once batch state and reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from .errors import HarnessError, HarnessErrorCode
from .models import ExecutionRequest, ProviderExecutionResult, Scope, digest_of
from .providers import VlmExecutionProvider


class BatchItemState(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BatchItem:
    item_id: UUID
    request: ExecutionRequest
    state: BatchItemState = BatchItemState.PENDING
    execution_id: UUID | None = None
    result_digest: str | None = None


@dataclass(frozen=True, slots=True)
class BatchManifest:
    batch_id: UUID
    scope: Scope
    items: tuple[BatchItem, ...]
    concurrency_limit: int
    profile_version: str

    def __post_init__(self) -> None:
        if not self.items or self.concurrency_limit < 1:
            raise ValueError("batch requires items and a positive concurrency bound")
        if any(item.request.scope != self.scope for item in self.items):
            raise HarnessError(
                HarnessErrorCode.BATCH_SCOPE_VIOLATION, "A batch may contain only one workspace."
            )

    @property
    def digest(self) -> str:
        return digest_of(self)


class BatchCoordinator:
    def __init__(self, provider: VlmExecutionProvider) -> None:
        self.provider = provider

    def submit_pending(self, manifest: BatchManifest) -> BatchManifest:
        active = sum(item.state == BatchItemState.SUBMITTED for item in manifest.items)
        result: list[BatchItem] = []
        for item in manifest.items:
            if item.state == BatchItemState.PENDING and active < manifest.concurrency_limit:
                receipt = self.provider.submit(item.request)
                result.append(
                    replace(item, state=BatchItemState.SUBMITTED, execution_id=receipt.execution_id)
                )
                active += 1
            else:
                result.append(item)
        return replace(manifest, items=tuple(result))

    def reconcile(self, manifest: BatchManifest) -> BatchManifest:
        result: list[BatchItem] = []
        for item in manifest.items:
            if item.execution_id is None or item.state not in {
                BatchItemState.SUBMITTED,
                BatchItemState.UNKNOWN,
            }:
                result.append(item)
                continue
            provider_state = self.provider.poll(item.execution_id)
            if provider_state == "completed":
                provider_result: ProviderExecutionResult = self.provider.fetch_result(
                    item.execution_id
                )
                result.append(
                    replace(
                        item,
                        state=BatchItemState.COMPLETED,
                        result_digest=provider_result.response_digest,
                    )
                )
            elif provider_state == "cancelled":
                result.append(replace(item, state=BatchItemState.CANCELLED))
            elif provider_state == "failed":
                result.append(replace(item, state=BatchItemState.FAILED))
            elif provider_state == "unknown":
                result.append(replace(item, state=BatchItemState.UNKNOWN))
            else:
                result.append(item)
        return replace(manifest, items=tuple(result))

    @staticmethod
    def terminal_success(manifest: BatchManifest) -> bool:
        return all(item.state == BatchItemState.COMPLETED for item in manifest.items)
