from __future__ import annotations

import csv
import io
import zipfile

from asd_kontur.support.generation import validate_docx
from asd_kontur.support.package_export import build_editable_id_package_archive


def test_editable_package_export_keeps_register_first_and_marks_missing_items() -> None:
    archive = build_editable_id_package_archive(
        package={"id_package_id": "package-1", "version": 3},
        register_manifest={
            "documents": [
                {
                    "ordinal": 2,
                    "role": "support.aosr",
                    "state": "generated_candidate",
                    "copies": 1,
                    "evidence_refs": ["rule:one"],
                },
                {
                    "ordinal": 3,
                    "role": "support.executive-scheme",
                    "state": "missing",
                    "copies": 1,
                    "evidence_refs": ["project:geometry"],
                },
            ]
        },
        memberships=(
            {"ordinal": 1, "role": "register"},
            {
                "ordinal": 2,
                "role": "support.aosr",
                "generated_candidate_id": "candidate-1",
                "object_reference": "objects/candidate-1.docx",
                "format": "DOCX",
                "blocker_codes": [],
            },
            {
                "ordinal": 3,
                "role": "support.executive-scheme",
                "state": "missing",
                "blocker_codes": ["GEOMETRY_UNCONFIRMED"],
            },
        ),
        field_resolutions=(
            {
                "generation_run_id": "run-1",
                "field_key": "work_description",
                "state": "confirmed",
                "material": True,
                "normalized_value": "concrete_work",
                "display_value": "Concrete work",
                "fact_id": "fact-1",
                "fact_version": 3,
                "evidence_link_id": "evidence-2",
                "source_locator_id": "locator-2",
            },
            {
                "generation_run_id": "run-1",
                "field_key": "work_description",
                "state": "confirmed",
                "material": True,
                "normalized_value": "concrete_work",
                "display_value": "Concrete work",
                "fact_id": "fact-1",
                "fact_version": 3,
                "evidence_link_id": "evidence-1",
                "source_locator_id": "locator-1",
            },
            {
                "generation_run_id": "run-1",
                "field_key": "as_built_level",
                "state": "missing",
                "material": True,
                "normalized_value": None,
                "display_value": None,
                "fact_id": None,
                "fact_version": None,
                "evidence_link_id": None,
                "source_locator_id": None,
            },
        ),
        read_object=lambda key: b"docx-bytes" if key.endswith("candidate-1.docx") else b"",
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as exported:
        assert exported.namelist() == [
            "01_register_candidate.docx",
            "01_register.csv",
            "02_support.aosr_candidate.docx",
            "97_field_evidence_and_missing_inputs.csv",
            "98_package_status.txt",
            "99_missing_or_blocked_items.csv",
        ]
        register = exported.read("01_register_candidate.docx")
        with zipfile.ZipFile(io.BytesIO(register)) as document:
            assert "word/document.xml" in document.namelist()
            content = document.read("word/document.xml").decode("utf-8")
        assert "Реестр исполнительной документации (кандидат)" in content
        assert "support.aosr" in content
        assert validate_docx(register, required_fields=()).valid
        rows = list(
            csv.DictReader(
                io.StringIO(exported.read("99_missing_or_blocked_items.csv").decode("utf-8-sig"))
            )
        )
        fields = list(
            csv.DictReader(
                io.StringIO(
                    exported.read("97_field_evidence_and_missing_inputs.csv").decode("utf-8-sig")
                )
            )
        )
    assert rows[0]["role"] == "support.executive-scheme"
    assert rows[0]["blockers"] == "GEOMETRY_UNCONFIRMED"
    assert [field["field_key"] for field in fields] == ["as_built_level", "work_description"]
    assert fields[0]["state"] == "missing"
    assert fields[0]["display_value"] == ""
    assert fields[1]["evidence_link_ids"] == "evidence-1;evidence-2"
    assert fields[1]["source_locator_ids"] == "locator-1;locator-2"
