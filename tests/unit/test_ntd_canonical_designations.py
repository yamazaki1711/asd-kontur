# ruff: noqa: RUF001 -- exact Cyrillic designation aliases are the behavior under test.

from asd_kontur.ntd.canonical_memory import _audit_input
from asd_kontur.ntd.search_corpus import designation_aliases, normalize_designation


def test_designation_aliases_cover_latin_cyrillic_and_number_only_forms() -> None:
    sp_aliases = {normalize_designation(value) for value in designation_aliases("СП 70.13330.2012")}
    gost_aliases = {
        normalize_designation(value) for value in designation_aliases("ГОСТ 10180-2012")
    }

    assert normalize_designation("СП70") in sp_aliases
    assert normalize_designation("SP70") in sp_aliases
    assert normalize_designation("70.13330.2012") in sp_aliases
    assert normalize_designation("ГОСТ10180") in gost_aliases
    assert normalize_designation("GOST10180") in gost_aliases


def test_exact_digest_metadata_override_repairs_instruction_identity() -> None:
    value = _audit_input(
        {
            "classification": "legacy/reference",
            "sha256": "sha256:400115a99fa3ec311395162f9bc5a7839062aad544ac1da484f0432a76057d16",
            "designation": "VSN 123-90",
            "title": "Incorrect audit identity",
            "size_bytes": 1,
            "mime": "application/pdf",
        }
    )

    assert value.designation == "И 1.13-07"
    assert value.title.startswith("Инструкция по оформлению")
    assert value.authority_class == "legacy_reference"
