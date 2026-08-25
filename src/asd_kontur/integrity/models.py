"""Typed, content-minimal records used by SYSTEM-INTEGRITY-CYCLE-01."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID


class ReadinessStatus(StrEnum):
    READY_FOR_INTEGRITY_CYCLE = "READY_FOR_INTEGRITY_CYCLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    CONTRACT_ONLY = "CONTRACT_ONLY"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class IntegrityFailure(RuntimeError):
    """A typed qualification blocker that must terminate the current cycle."""

    def __init__(self, code: str, message: str, *, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.evidence = evidence or {}


def _canonical_default(value: Any) -> Any:
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_default,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ModuleReadinessEntry:
    module_id: str
    version: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    schema_relations: tuple[str, ...]
    contract_keys: tuple[str, ...]
    qualification_checks: tuple[str, ...]
    lifecycle_participation: str
    backup_participation: str
    implemented_status: str
    qualification_status: ReadinessStatus
    known_gaps: tuple[str, ...]
    cycle_steps: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ModuleReadinessEntry:
        return cls(
            module_id=str(value["module_id"]),
            version=str(value["version"]),
            purpose=str(value["purpose"]),
            inputs=tuple(str(item) for item in value["inputs"]),
            outputs=tuple(str(item) for item in value["outputs"]),
            dependencies=tuple(str(item) for item in value["dependencies"]),
            schema_relations=tuple(str(item) for item in value["schema_relations"]),
            contract_keys=tuple(str(item) for item in value["contract_keys"]),
            qualification_checks=tuple(str(item) for item in value["qualification_checks"]),
            lifecycle_participation=str(value["lifecycle_participation"]),
            backup_participation=str(value["backup_participation"]),
            implemented_status=str(value["implemented_status"]),
            qualification_status=ReadinessStatus(value["qualification_status"]),
            known_gaps=tuple(str(item) for item in value["known_gaps"]),
            cycle_steps=tuple(str(item) for item in value["cycle_steps"]),
        )


@dataclass(frozen=True, slots=True)
class ModuleReadinessManifest:
    contract_version: str
    manifest_id: str
    code_baseline: str
    product_ready: bool
    modules: tuple[ModuleReadinessEntry, ...]

    @property
    def semantic_fingerprint(self) -> str:
        return canonical_digest(
            {
                "contract_version": self.contract_version,
                "manifest_id": self.manifest_id,
                "code_baseline": self.code_baseline,
                "product_ready": self.product_ready,
                "modules": [
                    {
                        "module_id": item.module_id,
                        "version": item.version,
                        "purpose": item.purpose,
                        "inputs": item.inputs,
                        "outputs": item.outputs,
                        "dependencies": item.dependencies,
                        "schema_relations": item.schema_relations,
                        "contract_keys": item.contract_keys,
                        "qualification_checks": item.qualification_checks,
                        "lifecycle_participation": item.lifecycle_participation,
                        "backup_participation": item.backup_participation,
                        "implemented_status": item.implemented_status,
                        "qualification_status": item.qualification_status.value,
                        "known_gaps": item.known_gaps,
                        "cycle_steps": item.cycle_steps,
                    }
                    for item in self.modules
                ],
            }
        )


def load_module_readiness_manifest(path: Path) -> ModuleReadinessManifest:
    value = json.loads(path.read_text(encoding="utf-8"))
    modules = tuple(ModuleReadinessEntry.from_dict(item) for item in value["modules"])
    identities = [item.module_id for item in modules]
    if len(identities) != len(set(identities)):
        raise IntegrityFailure("DUPLICATE_MODULE_IDENTITY", "module identities must be unique")
    for item in modules:
        if item.qualification_status is ReadinessStatus.READY_FOR_INTEGRITY_CYCLE:
            if not item.qualification_checks or not item.cycle_steps:
                raise IntegrityFailure(
                    "UNEXECUTABLE_READY_MODULE",
                    f"{item.module_id} is READY without executable qualification evidence",
                )
        if (
            item.qualification_status
            in {
                ReadinessStatus.PARTIAL,
                ReadinessStatus.BLOCKED,
                ReadinessStatus.CONTRACT_ONLY,
                ReadinessStatus.NOT_IMPLEMENTED,
            }
            and not item.known_gaps
        ):
            raise IntegrityFailure(
                "UNEXPLAINED_NON_READY_MODULE",
                f"{item.module_id} has no recorded gap",
            )
    return ModuleReadinessManifest(
        contract_version=str(value["contract_version"]),
        manifest_id=str(value["manifest_id"]),
        code_baseline=str(value["code_baseline"]),
        product_ready=bool(value["product_ready"]),
        modules=modules,
    )


def write_immutable_json(path: Path, value: Any) -> None:
    """Write one fsynced receipt without allowing historical replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if not path.exists():
            raise
        raise
