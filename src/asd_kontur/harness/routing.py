"""Version-pinned, fail-closed routing and cost reservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .models import Route, Scope, digest_of


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    key: str
    version: str
    environment: str
    external_active: bool
    allowed_external_classifications: frozenset[str]
    allowed_external_purposes: frozenset[str]
    provider_terms_active: bool
    raw_artifact_policy: str


@dataclass(frozen=True, slots=True)
class RoutingContext:
    scope: Scope
    classification: str | None
    purpose: str
    workspace_writable: bool
    native_sufficient: bool
    local_available: bool
    local_qualified: bool
    external_available: bool
    external_qualified: bool
    egress_authorized: bool
    budget_reserved: bool
    legal_or_geometry: bool
    mass_raster: bool


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    route: Route
    decision: str
    considered_routes: tuple[Route, ...]
    rejected: tuple[tuple[Route, str], ...]
    policy_version: str
    authorization_ref: str | None
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "digest",
            digest_of(
                {
                    "route": self.route,
                    "decision": self.decision,
                    "considered_routes": self.considered_routes,
                    "rejected": self.rejected,
                    "policy_version": self.policy_version,
                    "authorization_ref": self.authorization_ref,
                }
            ),
        )


def route(
    context: RoutingContext, policy: RoutingPolicy, *, authorization_ref: str | None
) -> RoutingDecision:
    considered = (
        Route.NATIVE_ONLY,
        Route.LOCAL_VLM,
        Route.AUTHORIZED_EXTERNAL_VLM,
        Route.NO_EXECUTION,
    )
    rejected: list[tuple[Route, str]] = []
    if not context.workspace_writable:
        return RoutingDecision(
            Route.NO_EXECUTION,
            "blocked",
            considered,
            ((Route.NO_EXECUTION, "workspace.not_writable"),),
            policy.version,
            None,
        )
    if context.native_sufficient:
        return RoutingDecision(
            Route.NATIVE_ONLY, "allowed", considered, (), policy.version, authorization_ref
        )
    if context.local_available and context.local_qualified:
        return RoutingDecision(
            Route.LOCAL_VLM, "allowed", considered, (), policy.version, authorization_ref
        )
    rejected.append((Route.LOCAL_VLM, "local.unavailable_or_unqualified"))
    classification = context.classification
    external_allowed = all(
        (
            policy.external_active,
            policy.provider_terms_active,
            context.external_available,
            context.external_qualified,
            context.egress_authorized,
            context.budget_reserved,
            classification is not None,
            classification in policy.allowed_external_classifications if classification else False,
            context.purpose in policy.allowed_external_purposes,
            not context.legal_or_geometry,
            context.mass_raster,
            authorization_ref is not None,
        )
    )
    if external_allowed:
        return RoutingDecision(
            Route.AUTHORIZED_EXTERNAL_VLM,
            "allowed",
            considered,
            tuple(rejected),
            policy.version,
            authorization_ref,
        )
    rejected.append((Route.AUTHORIZED_EXTERNAL_VLM, "external.policy_or_authority_denied"))
    return RoutingDecision(
        Route.NO_EXECUTION, "denied", considered, tuple(rejected), policy.version, None
    )


@dataclass(frozen=True, slots=True)
class CostEnvelope:
    envelope_id: UUID
    version: str
    scope: Scope
    purpose: str
    provider_profile: str
    currency: str
    committed_maximum: Decimal
    per_item_maximum: Decimal
    stop_threshold: Decimal
    valid_until: datetime
    authorizing_principal: str


class CostLedger:
    def __init__(self, envelope: CostEnvelope) -> None:
        self.envelope = envelope
        self._reserved: dict[str, Decimal] = {}
        self._committed = Decimal("0")

    def reserve(self, item_key: str, amount: Decimal, now: datetime) -> bool:
        if (
            now >= self.envelope.valid_until
            or amount < 0
            or amount > self.envelope.per_item_maximum
        ):
            return False
        remaining = (
            self.envelope.committed_maximum
            - self._committed
            - sum(self._reserved.values(), Decimal("0"))
        )
        if remaining - amount <= self.envelope.stop_threshold:
            return False
        self._reserved.setdefault(item_key, amount)
        return self._reserved[item_key] == amount

    def commit(self, item_key: str, actual: Decimal) -> None:
        reserved = self._reserved.pop(item_key)
        if actual > reserved:
            raise ValueError("actual cost exceeds its reservation")
        self._committed += actual

    def release(self, item_key: str) -> None:
        self._reserved.pop(item_key, None)

    @property
    def remaining(self) -> Decimal:
        return (
            self.envelope.committed_maximum
            - self._committed
            - sum(self._reserved.values(), Decimal("0"))
        )
