"""Deterministic native-first and resource-aware corpus planning."""

from __future__ import annotations

from uuid import UUID

from asd_kontur.domain import uuid7

from .models import (
    Composition,
    CorpusOutcome,
    PagePlan,
    PageRoute,
    PhysicalObjectInspection,
    ProcessingPlan,
    ProcessingShard,
    ResourcePolicy,
)


def build_processing_plan(
    inspection: PhysicalObjectInspection,
    *,
    purpose: str,
    classification: str,
    policy: ResourcePolicy,
    sensitive: bool = False,
    boundary_hints: frozenset[int] = frozenset(),
) -> ProcessingPlan:
    """Plan exact pages without widening egress or blindly selecting local VLM."""
    page_plans: list[PagePlan] = []
    raster_pages = sum(page.composition is Composition.RASTER for page in inspection.pages)
    huge_for_local = (
        inspection.page_count > policy.max_local_pages
        or inspection.size_bytes > policy.max_local_bytes
        or raster_pages > policy.max_local_pages
    )
    for page in inspection.pages:
        composition = page.composition
        if not page.readable:
            route, reason, cost = PageRoute.BLOCKED, "PAGE_UNREADABLE", 0
        elif composition is Composition.NATIVE:
            route, reason, cost = PageRoute.NATIVE, "NATIVE_TEXT_AVAILABLE", 1
        elif composition is Composition.MIXED and page.native_text_characters >= 80:
            route, reason, cost = PageRoute.DETERMINISTIC, "MIXED_NATIVE_SUFFICIENT", 2
        elif huge_for_local:
            if sensitive:
                route, reason, cost = PageRoute.DEFERRED, "SENSITIVE_HUGE_LOCAL_LIMIT", 0
            elif policy.external_egress_allowed and policy.external_provider_qualified:
                route, reason, cost = PageRoute.EXTERNAL_ELIGIBLE, "MASS_RASTER_ELIGIBLE", 4
            else:
                route, reason, cost = PageRoute.DEFERRED, "EXTERNAL_ROUTE_UNAVAILABLE", 0
        else:
            route, reason, cost = PageRoute.LOCAL_VLM, "BOUNDED_RASTER_LOCAL", 8
        page_plans.append(PagePlan(page.page_number, route, reason, cost))

    plan_id = uuid7()
    shards = _build_shards(plan_id, tuple(page_plans), policy, boundary_hints)
    estimated_cost = sum(page.estimated_cost_units for page in page_plans)
    if any(page.route is PageRoute.BLOCKED for page in page_plans):
        state = CorpusOutcome.BLOCKED
    elif any(page.route is PageRoute.DEFERRED for page in page_plans):
        state = CorpusOutcome.PARTIAL
    elif estimated_cost > policy.max_total_cost_units:
        page_plans = [
            PagePlan(page.page_number, PageRoute.DEFERRED, "BUDGET_EXHAUSTED", 0)
            if page.route not in {PageRoute.NATIVE, PageRoute.DETERMINISTIC}
            else page
            for page in page_plans
        ]
        shards = _build_shards(plan_id, tuple(page_plans), policy, boundary_hints)
        estimated_cost = sum(page.estimated_cost_units for page in page_plans)
        state = CorpusOutcome.PARTIAL
    else:
        state = CorpusOutcome.COMPLETE
    return ProcessingPlan(
        inspection.scope,
        plan_id,
        1,
        inspection.inspection_id,
        purpose,
        classification,
        policy.policy_version,
        tuple(page_plans),
        shards,
        estimated_cost,
        max(1, estimated_cost * 2),
        state,
    )


def _build_shards(
    plan_id: UUID,
    page_plans: tuple[PagePlan, ...],
    policy: ResourcePolicy,
    boundary_hints: frozenset[int],
) -> tuple[ProcessingShard, ...]:
    result: list[ProcessingShard] = []
    ordinal = 1
    current_route: PageRoute | None = None
    current_pages: list[int] = []

    def flush() -> None:
        nonlocal ordinal, current_pages
        if not current_pages or current_route is None:
            return
        size = (
            policy.max_raster_pages_per_shard
            if current_route in {PageRoute.LOCAL_VLM, PageRoute.EXTERNAL_ELIGIBLE}
            else policy.max_pages_per_shard
        )
        for offset in range(0, len(current_pages), size):
            exact = tuple(current_pages[offset : offset + size])
            result.append(
                ProcessingShard(
                    uuid7(),
                    plan_id,
                    ordinal,
                    exact,
                    (),
                    current_route,
                    "urn:asd-kontur:contracts:v1.4:audit:processing-receipt",
                )
            )
            ordinal += 1
        current_pages = []

    for page in page_plans:
        if page.route in {PageRoute.BLOCKED, PageRoute.DEFERRED}:
            flush()
            current_route = None
            continue
        if current_route is not None and (
            page.route is not current_route or page.page_number in boundary_hints
        ):
            flush()
        current_route = page.route
        current_pages.append(page.page_number)
    flush()
    return tuple(result)


def pages_for_resume(plan: ProcessingPlan, successful_pages: frozenset[int]) -> tuple[int, ...]:
    """Return only executable pages not already validated under this exact plan."""
    return tuple(
        page.page_number
        for page in plan.page_plans
        if page.page_number not in successful_pages
        and page.route not in {PageRoute.BLOCKED, PageRoute.DEFERRED}
    )
