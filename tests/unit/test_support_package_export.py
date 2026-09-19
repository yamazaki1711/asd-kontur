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
        read_object=lambda key: b"docx-bytes" if key.endswith("candidate-1.docx") else b"",
    )

    with zipfile.ZipFile(io.BytesIO(archive)) as exported:
        assert exported.namelist() == [
            "01_register_candidate.docx",
            "01_register.csv",
            "02_support.aosr_candidate.docx",
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
    assert rows[0]["role"] == "support.executive-scheme"
    assert rows[0]["blockers"] == "GEOMETRY_UNCONFIRMED"
