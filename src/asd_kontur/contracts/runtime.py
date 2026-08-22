"""Standards-conformant, offline-only runtime for Contract Pack v0.1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import ContractErrorCode, ContractValidationError, ValidationIssue

JsonObject = dict[str, Any]
EXPECTED_REGISTRY_VERSION = "0.1.0"
EXPECTED_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()


class ContractRegistry:
    """Load and validate the immutable local Contract Pack bundle."""

    def __init__(
        self,
        root: Path,
        registry_document: JsonObject,
        schemas: Mapping[str, JsonObject],
    ) -> None:
        self.root = root
        self.document = registry_document
        self.schemas = dict(schemas)
        resources = [
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in self.schemas.items()
        ]
        self._ref_registry = Registry().with_resources(resources)
        self._contract_groups = {
            key: group
            for group in self.document["contract_groups"]
            for key in group["contract_keys"]
        }

    @classmethod
    def load(cls, root: Path) -> ContractRegistry:
        root = root.resolve()
        registry_path = root / "registry.json"
        document = cls._load_json(registry_path)
        cls._validate_registry_header(document)
        schemas: dict[str, JsonObject] = {}
        for item in document["schemas"]:
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root):
                raise cls._failure("schema path escapes Contract Pack root")
            schema = cls._load_json(path)
            schema_id = schema.get("$id")
            if schema_id != item["schema_id"]:
                raise cls._failure(f"schema identity mismatch for {path.name}")
            if schema_id in schemas:
                raise cls._failure(f"duplicate schema $id: {schema_id}")
            if schema.get("$schema") != EXPECTED_SCHEMA_DIALECT:
                raise cls._failure(f"unsupported schema dialect: {path.name}")
            actual_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_digest != item["digest"]:
                raise cls._failure(f"schema fingerprint mismatch: {path.name}")
            schemas[schema_id] = schema
        if len(schemas) != 13:
            raise cls._failure(f"expected 13 unique schemas, found {len(schemas)}")
        cls._validate_local_references(schemas)
        return cls(root, document, schemas)

    @staticmethod
    def _load_json(path: Path) -> JsonObject:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractRegistry._failure(f"cannot load JSON: {path}") from exc
        if not isinstance(value, dict):
            raise ContractRegistry._failure(f"JSON root must be an object: {path}")
        return value

    @staticmethod
    def _validate_registry_header(document: JsonObject) -> None:
        if document.get("registry_version") != EXPECTED_REGISTRY_VERSION:
            raise ContractRegistry._failure("unsupported Contract Registry version")
        if document.get("schema_dialect") != EXPECTED_SCHEMA_DIALECT:
            raise ContractRegistry._failure("unsupported Contract Registry schema dialect")

    @staticmethod
    def _walk_references(value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str):
                yield reference
            for child in value.values():
                yield from ContractRegistry._walk_references(child)
        elif isinstance(value, list):
            for child in value:
                yield from ContractRegistry._walk_references(child)

    @staticmethod
    def _validate_local_references(schemas: Mapping[str, JsonObject]) -> None:
        for schema_id, schema in schemas.items():
            for reference in ContractRegistry._walk_references(schema):
                if reference.startswith("#"):
                    ContractRegistry._resolve_pointer(schema, reference)
                    continue
                target_id, separator, fragment = reference.partition("#")
                if not target_id.startswith("urn:asd-kontur:contracts:v0.1:schema:"):
                    raise ContractRegistry._failure(
                        f"network or foreign schema resolution forbidden: {reference}"
                    )
                target = schemas.get(target_id)
                if target is None:
                    raise ContractRegistry._failure(f"unresolved local $ref: {reference}")
                if separator:
                    ContractRegistry._resolve_pointer(target, "#" + fragment)
            if schema["$id"] != schema_id:
                raise ContractRegistry._failure(f"schema store identity mismatch: {schema_id}")

    @staticmethod
    def _resolve_pointer(document: JsonObject, pointer: str) -> JsonObject:
        if pointer in ("", "#"):
            return document
        value: Any = document
        fragment = pointer.removeprefix("#")
        if not fragment.startswith("/"):
            raise ContractRegistry._failure(f"unsupported JSON Pointer: {pointer}")
        try:
            for part in fragment[1:].split("/"):
                token = part.replace("~1", "/").replace("~0", "~")
                value = value[int(token)] if isinstance(value, list) else value[token]
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ContractRegistry._failure(f"unresolved JSON Pointer: {pointer}") from exc
        if not isinstance(value, dict):
            raise ContractRegistry._failure(f"schema pointer is not an object: {pointer}")
        return value

    def contract_family(self, contract_key: str, contract_version: str) -> str:
        if contract_version == "latest":
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.INCOMPATIBLE_VERSION,
                    "mutable latest is forbidden",
                )
            )
        expected = self.document["release_defaults"]["contract_version"]
        if contract_version != expected:
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.UNKNOWN_VERSION,
                    f"unsupported contract version: {contract_version}",
                )
            )
        group = self._contract_groups.get(contract_key)
        if group is None:
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.UNKNOWN_VERSION,
                    f"unknown contract key: {contract_key}",
                )
            )
        return str(group["contract_family"])

    def validate(
        self,
        *,
        contract_key: str,
        contract_version: str,
        schema_id: str,
        schema_pointer: str,
        payload: Mapping[str, Any],
    ) -> ValidationResult:
        self.contract_family(contract_key, contract_version)
        if self._contains_latest(payload):
            return ValidationResult(
                False,
                (
                    ValidationIssue(
                        ContractErrorCode.INCOMPATIBLE_VERSION,
                        "mutable latest is forbidden in persisted payloads",
                    ),
                ),
            )
        schema = self.schemas.get(schema_id)
        if schema is None:
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.UNKNOWN_VERSION,
                    f"unknown schema identity: {schema_id}",
                )
            )
        group = self._contract_groups[contract_key]
        if group["schema_id"] != schema_id:
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.INCOMPATIBLE_VERSION,
                    "contract key is not registered for the selected schema",
                )
            )
        fragment = self._resolve_pointer(schema, schema_pointer)
        root_validator = Draft202012Validator(
            schema,
            registry=self._ref_registry,
            format_checker=FormatChecker(),
        )
        validator = root_validator.evolve(schema=fragment)
        schema_error_code = (
            ContractErrorCode.CANDIDATE_INVALID
            if schema_id.endswith(":candidate-fact")
            else ContractErrorCode.INVALID_SCHEMA
        )
        issues = tuple(
            ValidationIssue(
                schema_error_code,
                error.message,
                self._json_path(error.absolute_path),
                "/".join(str(part) for part in error.absolute_schema_path),
            )
            for error in sorted(validator.iter_errors(dict(payload)), key=str)
        )
        return ValidationResult(not issues, issues)

    @staticmethod
    def canonicalize(payload: Mapping[str, Any], *, omit_digest: bool = True) -> bytes:
        projected = dict(payload)
        if omit_digest:
            projected.pop("digest", None)
        try:
            return rfc8785.dumps(projected)
        except (rfc8785.CanonicalizationError, TypeError) as exc:
            raise ContractValidationError(
                ValidationIssue(
                    ContractErrorCode.INVALID_SCHEMA,
                    "payload cannot be represented as RFC 8785 canonical JSON",
                )
            ) from exc

    @classmethod
    def digest(cls, payload: Mapping[str, Any], *, omit_digest: bool = True) -> str:
        canonical = cls.canonicalize(payload, omit_digest=omit_digest)
        return "sha256:" + hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _contains_latest(value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"contract_version", "schema_version", "version"} and child == "latest":
                    return True
                if ContractRegistry._contains_latest(child):
                    return True
        elif isinstance(value, list):
            return any(ContractRegistry._contains_latest(item) for item in value)
        return False

    @staticmethod
    def _json_path(parts: Iterable[Any]) -> str:
        result = "$"
        for part in parts:
            result += f"[{part}]" if isinstance(part, int) else f".{part}"
        return result

    @staticmethod
    def _failure(message: str) -> ContractValidationError:
        return ContractValidationError(ValidationIssue(ContractErrorCode.INVALID_SCHEMA, message))
