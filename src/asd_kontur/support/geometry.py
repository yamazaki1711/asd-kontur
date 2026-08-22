"""Confirmed-geometry guard and deterministic executive-scheme semantics."""

from __future__ import annotations

from decimal import Decimal

from asd_kontur.harness.models import digest_of

from .models import ExecutiveSchemeResult, GeometryInput, GeometryOutcome


def form_executive_scheme(
    *,
    design: GeometryInput,
    as_built: GeometryInput,
    tolerance: Decimal,
    tolerance_unit: str,
    boundary_inclusive: bool,
) -> ExecutiveSchemeResult:
    blockers: list[str] = []
    for value, prefix in ((design, "DESIGN"), (as_built, "AS_BUILT")):
        if not value.confirmed:
            blockers.append(f"{prefix}_GEOMETRY_UNCONFIRMED")
        if value.confirmation_identity_kind in {"model", "service", "integration"}:
            blockers.append(f"{prefix}_AUTHORITY_INVALID")
        if not value.crs_ref:
            blockers.append(f"{prefix}_CRS_MISSING")
        if not value.reference_frame_ref:
            blockers.append(f"{prefix}_FRAME_MISSING")
        if not value.unit_code:
            blockers.append(f"{prefix}_UNIT_MISSING")
        if value.precision_scale is None:
            blockers.append(f"{prefix}_PRECISION_MISSING")
        if not value.points:
            blockers.append(f"{prefix}_POINTS_MISSING")
    if not as_built.calibration_valid:
        blockers.append("AS_BUILT_CALIBRATION_INVALID")
    if design.crs_ref != as_built.crs_ref:
        blockers.append("CRS_MISMATCH")
    if design.reference_frame_ref != as_built.reference_frame_ref:
        blockers.append("FRAME_MISMATCH")
    if design.unit_code != as_built.unit_code or design.unit_code != tolerance_unit:
        blockers.append("GEOMETRY_UNIT_MISMATCH")
    if len(design.points) != len(as_built.points):
        blockers.append("GEOMETRY_CARDINALITY_MISMATCH")
    if blockers:
        return ExecutiveSchemeResult(
            GeometryOutcome.BLOCKED,
            None,
            (),
            tuple(sorted(set(blockers))),
        )

    outcomes: list[str] = []
    deltas: list[tuple[str, str]] = []
    for designed, observed in zip(design.points, as_built.points, strict=True):
        dx = abs(observed[0] - designed[0])
        dy = abs(observed[1] - designed[1])
        maximum = max(dx, dy)
        within = maximum <= tolerance if boundary_inclusive else maximum < tolerance
        outcomes.append("within_tolerance" if within else "outside_tolerance")
        deltas.append((str(dx), str(dy)))
    fingerprint = digest_of(
        {
            "design": _geometry_payload(design),
            "as_built": _geometry_payload(as_built),
            "tolerance": str(tolerance),
            "tolerance_unit": tolerance_unit,
            "boundary_inclusive": boundary_inclusive,
            "deltas": deltas,
            "outcomes": outcomes,
        }
    )
    return ExecutiveSchemeResult(
        GeometryOutcome.ELIGIBLE,
        fingerprint,
        tuple(outcomes),
        (),
    )


def _geometry_payload(value: GeometryInput) -> dict[str, object]:
    return {
        "geometry_input_id": value.geometry_input_id,
        "geometry_kind": value.geometry_kind,
        "fact_id": value.fact_id,
        "fact_version": value.fact_version,
        "source_version_id": value.source_version_id,
        "source_locator_id": value.source_locator_id,
        "crs_ref": value.crs_ref,
        "reference_frame_ref": value.reference_frame_ref,
        "unit_code": value.unit_code,
        "precision_scale": value.precision_scale,
        "points": tuple((str(x), str(y)) for x, y in value.points),
        "confirmed": value.confirmed,
        "confirmation_identity_kind": value.confirmation_identity_kind,
        "measurement_method_ref": value.measurement_method_ref,
        "calibration_valid": value.calibration_valid,
    }
