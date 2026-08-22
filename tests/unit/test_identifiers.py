from __future__ import annotations

import uuid

from asd_kontur.domain import deterministic_uuid, uuid7, uuid7_from_parts


def test_uuid7_rfc_9562_layout_vector() -> None:
    value = uuid7_from_parts(
        timestamp_ms=0x0123456789AB,
        random_a=0xCDE,
        random_b=0x0123456789ABCDEF,
    )

    assert str(value) == "01234567-89ab-7cde-8123-456789abcdef"
    assert value.version == 7
    assert value.variant == uuid.RFC_4122
    assert value.int >> 80 == 0x0123456789AB


def test_generated_uuid7_has_required_version_and_variant() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_registered_uuid5_is_deterministic_and_normalized() -> None:
    expected = uuid.UUID("cc9eff50-67df-578c-a185-0e7f440e02db")

    assert deterministic_uuid("work-type.synthetic") == expected
    assert deterministic_uuid(" work-type.synthetic ") == expected
    assert deterministic_uuid("e\u0301") == deterministic_uuid("é")


def test_semantic_identity_does_not_case_fold() -> None:
    assert deterministic_uuid("Work-Type") != deterministic_uuid("work-type")
