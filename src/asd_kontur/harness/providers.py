"""Provider boundary: local process isolation and deterministic no-network test provider."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import UUID

from asd_kontur.domain import uuid7

from .errors import HarnessError, HarnessErrorCode
from .models import (
    ExecutionIdentity,
    ExecutionRequest,
    ProviderExecutionResult,
    ProviderState,
    digest_of,
)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider_key: str
    provider_version: str
    synchronous: bool
    batch: bool
    cancellation: bool
    structured_output: bool
    network_egress: bool


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    available: bool
    reason_code: str
    observed_at: datetime
    qualified: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    execution_id: UUID
    request_id: UUID
    attempt_id: UUID
    state: ProviderState
    duplicate: bool


@dataclass(frozen=True, slots=True)
class CancellationReceipt:
    execution_id: UUID
    state: ProviderState
    reason: str


class VlmExecutionProvider(Protocol):
    def describe_capabilities(self) -> ProviderCapabilities: ...
    def health(self, profile_ref: str) -> ProviderHealth: ...
    def submit(self, request: ExecutionRequest) -> ExecutionReceipt: ...
    def poll(self, execution_id: UUID) -> ProviderState: ...
    def cancel(self, execution_id: UUID, reason: str) -> CancellationReceipt: ...
    def fetch_result(self, execution_id: UUID) -> ProviderExecutionResult: ...


class DeterministicExternalProvider:
    """Async provider test double. It never performs network I/O."""

    def __init__(self, responder: Callable[[ExecutionRequest], dict[str, object]]) -> None:
        self._responder = responder
        self._requests: dict[UUID, ExecutionRequest] = {}
        self._by_key: dict[tuple[UUID, str], UUID] = {}
        self._states: dict[UUID, ProviderState] = {}
        self._results: dict[UUID, ProviderExecutionResult] = {}
        self._lock = Lock()

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            "provider.synthetic.external", "1.0.0", False, True, True, True, False
        )

    def health(self, profile_ref: str) -> ProviderHealth:
        return ProviderHealth(True, "synthetic.available", datetime.now(UTC), qualified=False)

    def submit(self, request: ExecutionRequest) -> ExecutionReceipt:
        key = (request.scope.workspace_id, request.idempotency_key)
        with self._lock:
            prior = self._by_key.get(key)
            if prior is not None:
                previous = self._requests[prior]
                if previous.request_digest != request.request_digest:
                    raise HarnessError(
                        HarnessErrorCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                        "Idempotency key conflicts with an earlier request.",
                    )
                return ExecutionReceipt(
                    prior, request.request_id, request.attempt_id, self._states[prior], True
                )
            execution_id = uuid7()
            self._by_key[key] = execution_id
            self._requests[execution_id] = request
            self._states[execution_id] = ProviderState.PENDING
            return ExecutionReceipt(
                execution_id, request.request_id, request.attempt_id, ProviderState.PENDING, False
            )

    def complete(self, execution_id: UUID) -> ProviderExecutionResult:
        with self._lock:
            request = self._requests[execution_id]
            payload = self._responder(request)
            result = ProviderExecutionResult(
                execution_id,
                request.request_id,
                request.attempt_id,
                request.scope,
                request.identity,
                ProviderState.COMPLETED,
                "synthetic.completed",
                request.request_digest,
                digest_of(payload),
                payload,
                datetime.now(UTC),
            )
            self._results[execution_id] = result
            self._states[execution_id] = ProviderState.COMPLETED
            return result

    def mark_unknown(self, execution_id: UUID) -> None:
        self._states[execution_id] = ProviderState.UNKNOWN

    def poll(self, execution_id: UUID) -> ProviderState:
        return self._states.get(execution_id, ProviderState.UNKNOWN)

    def cancel(self, execution_id: UUID, reason: str) -> CancellationReceipt:
        if execution_id not in self._states:
            return CancellationReceipt(execution_id, ProviderState.UNKNOWN, reason)
        if self._states[execution_id] not in {ProviderState.COMPLETED, ProviderState.FAILED}:
            self._states[execution_id] = ProviderState.CANCELLED
        return CancellationReceipt(execution_id, self._states[execution_id], reason)

    def fetch_result(self, execution_id: UUID) -> ProviderExecutionResult:
        state = self.poll(execution_id)
        if state == ProviderState.UNKNOWN:
            raise HarnessError(
                HarnessErrorCode.PROVIDER_UNKNOWN_OUTCOME,
                "Provider outcome requires reconciliation.",
            )
        if state != ProviderState.COMPLETED:
            raise HarnessError(
                HarnessErrorCode.PROVIDER_FAILURE, "Provider execution has no completed result."
            )
        return self._results[execution_id]


@dataclass(frozen=True, slots=True)
class LocalProcessProfile:
    python_executable: Path
    runner_script: Path
    model_path: Path
    identity: ExecutionIdentity
    timeout_seconds: float
    stdout_limit_bytes: int = 65_536
    stderr_limit_bytes: int = 65_536


class LocalQwenProcessProvider:
    """MLX-independent process boundary; configuration paths are never persisted."""

    def __init__(self, profile: LocalProcessProfile) -> None:
        self.profile = profile
        self._results: dict[UUID, ProviderExecutionResult] = {}
        self._receipts: dict[tuple[UUID, str], ExecutionReceipt] = {}
        self._states: dict[UUID, ProviderState] = {}
        self._processes: dict[UUID, subprocess.Popen[bytes]] = {}
        self._process_lock = Lock()
        self._heavy_session_lock = Lock()

    def describe_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("provider.local.qwen", "1.0.0", True, True, True, True, False)

    def health(self, profile_ref: str) -> ProviderHealth:
        available = (
            self.profile.python_executable.is_file()
            and self.profile.runner_script.is_file()
            and self.profile.model_path.exists()
        )
        return ProviderHealth(
            available,
            "local.runtime.available" if available else "local.runtime.unavailable",
            datetime.now(UTC),
            qualified=False,
        )

    def submit(self, request: ExecutionRequest) -> ExecutionReceipt:
        key = (request.scope.workspace_id, request.idempotency_key)
        previous = self._receipts.get(key)
        if previous is not None:
            return ExecutionReceipt(
                previous.execution_id, request.request_id, request.attempt_id, previous.state, True
            )
        if request.identity != self.profile.identity:
            raise HarnessError(
                HarnessErrorCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                "Execution identity does not match the configured local profile.",
            )
        execution_id = uuid7()
        receipt = ExecutionReceipt(
            execution_id, request.request_id, request.attempt_id, ProviderState.RUNNING, False
        )
        self._receipts[key] = receipt
        self._states[execution_id] = ProviderState.RUNNING
        self._run(execution_id, request)
        return ExecutionReceipt(
            execution_id, request.request_id, request.attempt_id, self.poll(execution_id), False
        )

    def submit_bounded_batch(
        self, requests: tuple[ExecutionRequest, ...]
    ) -> tuple[ExecutionReceipt, ...]:
        """Execute one workspace batch in one process/model session."""
        if not requests:
            return ()
        if len({item.scope for item in requests}) != 1:
            raise HarnessError(
                HarnessErrorCode.BATCH_SCOPE_VIOLATION,
                "A local model session may contain only one workspace.",
            )
        if (
            len({item.identity for item in requests}) != 1
            or requests[0].identity != self.profile.identity
        ):
            raise HarnessError(
                HarnessErrorCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                "A local batch requires one exact execution identity.",
            )
        if not self._heavy_session_lock.acquire(blocking=False):
            raise HarnessError(
                HarnessErrorCode.PROVIDER_FAILURE,
                "A heavy local model session is already active.",
            )
        try:
            return self._submit_bounded_batch_locked(requests)
        finally:
            self._heavy_session_lock.release()

    def _submit_bounded_batch_locked(
        self, requests: tuple[ExecutionRequest, ...]
    ) -> tuple[ExecutionReceipt, ...]:
        if not self.health(requests[0].identity.execution_profile).available:
            raise HarnessError(HarnessErrorCode.PROVIDER_FAILURE, "Local runtime is unavailable.")
        executions = tuple((uuid7(), item) for item in requests)
        wire_requests = [
            {
                "request_id": str(item.request_id),
                "attempt_id": str(item.attempt_id),
                "source_digest": item.source_digest,
                "locators": [
                    {"page": locator.page, "region": locator.region} for locator in item.locators
                ],
                "purpose": item.purpose,
                "schema_version": item.identity.schema_version,
                "request_digest": item.request_digest,
                "identity_fingerprint": item.identity.fingerprint,
            }
            for _, item in executions
        ]
        with tempfile.TemporaryDirectory(prefix="asd_g07_local_batch_") as root:
            input_path = Path(root) / "request.json"
            output_path = Path(root) / "result.json"
            input_path.write_text(
                json.dumps({"requests": wire_requests}, sort_keys=True), encoding="utf-8"
            )
            completed = subprocess.run(
                [
                    str(self.profile.python_executable),
                    str(self.profile.runner_script),
                    "--model",
                    str(self.profile.model_path),
                    "--request",
                    str(input_path),
                    "--result",
                    str(output_path),
                ],
                capture_output=True,
                timeout=self.profile.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0 or not output_path.is_file():
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE, "Bounded local session failed."
                )
            wire = json.loads(output_path.read_text(encoding="utf-8"))
            results = wire.get("results") if isinstance(wire, dict) else None
            if not isinstance(results, list) or len(results) != len(executions):
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE,
                    "Bounded local session returned an incomplete result set.",
                )
            receipts: list[ExecutionReceipt] = []
            for (execution_id, request), result in zip(executions, results, strict=True):
                if (
                    not isinstance(result, dict)
                    or result.get("request_digest") != request.request_digest
                    or result.get("identity_fingerprint") != request.identity.fingerprint
                    or not isinstance(result.get("structured_payload"), dict)
                ):
                    raise HarnessError(
                        HarnessErrorCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                        "Bounded local result failed integrity checks.",
                    )
                payload = result["structured_payload"]
                assert isinstance(payload, dict)
                self._results[execution_id] = ProviderExecutionResult(
                    execution_id,
                    request.request_id,
                    request.attempt_id,
                    request.scope,
                    request.identity,
                    ProviderState.COMPLETED,
                    "local.batch.completed",
                    request.request_digest,
                    digest_of(payload),
                    payload,
                    datetime.now(UTC),
                )
                self._states[execution_id] = ProviderState.COMPLETED
                receipt = ExecutionReceipt(
                    execution_id,
                    request.request_id,
                    request.attempt_id,
                    ProviderState.COMPLETED,
                    False,
                )
                self._receipts[(request.scope.workspace_id, request.idempotency_key)] = receipt
                receipts.append(receipt)
            return tuple(receipts)

    def _run(self, execution_id: UUID, request: ExecutionRequest) -> None:
        if not self.health(request.identity.execution_profile).available:
            raise HarnessError(HarnessErrorCode.PROVIDER_FAILURE, "Local runtime is unavailable.")
        request_payload = {
            "request_id": str(request.request_id),
            "attempt_id": str(request.attempt_id),
            "source_digest": request.source_digest,
            "locators": [{"page": item.page, "region": item.region} for item in request.locators],
            "purpose": request.purpose,
            "schema_version": request.identity.schema_version,
            "request_digest": request.request_digest,
            "identity_fingerprint": request.identity.fingerprint,
        }
        with tempfile.TemporaryDirectory(prefix="asd_g07_local_") as root:
            input_path = Path(root) / "request.json"
            output_path = Path(root) / "result.json"
            input_path.write_text(json.dumps(request_payload, sort_keys=True), encoding="utf-8")
            argv = [
                str(self.profile.python_executable),
                str(self.profile.runner_script),
                "--model",
                str(self.profile.model_path),
                "--request",
                str(input_path),
                "--result",
                str(output_path),
            ]
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self._process_lock:
                self._processes[execution_id] = process
            try:
                stdout, stderr = process.communicate(timeout=self.profile.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                self._states[execution_id] = ProviderState.FAILED
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE,
                    "Local execution timed out and was terminated.",
                ) from exc
            finally:
                with self._process_lock:
                    self._processes.pop(execution_id, None)
            if self._states.get(execution_id) == ProviderState.CANCELLED:
                return
            if (
                len(stdout) > self.profile.stdout_limit_bytes
                or len(stderr) > self.profile.stderr_limit_bytes
            ):
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE,
                    "Local execution output exceeded bounded diagnostic limits.",
                )
            if process.returncode != 0 or not output_path.is_file():
                self._states[execution_id] = ProviderState.FAILED
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE,
                    "Local execution failed without a trusted result.",
                )
            try:
                wire = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE, "Local execution returned malformed output."
                ) from exc
            if (
                wire.get("request_digest") != request.request_digest
                or wire.get("identity_fingerprint") != request.identity.fingerprint
            ):
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_RESULT_INTEGRITY_FAILED,
                    "Local result identity or request digest mismatched.",
                )
            payload = wire.get("structured_payload")
            if not isinstance(payload, dict):
                raise HarnessError(
                    HarnessErrorCode.PROVIDER_FAILURE, "Local result omitted structured output."
                )
            self._results[execution_id] = ProviderExecutionResult(
                execution_id,
                request.request_id,
                request.attempt_id,
                request.scope,
                request.identity,
                ProviderState.COMPLETED,
                "local.completed",
                request.request_digest,
                digest_of(payload),
                payload,
                datetime.now(UTC),
            )
            self._states[execution_id] = ProviderState.COMPLETED

    def poll(self, execution_id: UUID) -> ProviderState:
        return self._states.get(execution_id, ProviderState.UNKNOWN)

    def cancel(self, execution_id: UUID, reason: str) -> CancellationReceipt:
        with self._process_lock:
            process = self._processes.get(execution_id)
            if process is not None:
                process.terminate()
                self._states[execution_id] = ProviderState.CANCELLED
        return CancellationReceipt(execution_id, self.poll(execution_id), reason)

    def fetch_result(self, execution_id: UUID) -> ProviderExecutionResult:
        try:
            return self._results[execution_id]
        except KeyError as exc:
            raise HarnessError(
                HarnessErrorCode.PROVIDER_UNKNOWN_OUTCOME,
                "Local result is unavailable and requires reconciliation.",
            ) from exc
