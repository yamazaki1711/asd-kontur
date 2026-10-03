from __future__ import annotations

from asd_kontur.support.package_consistency import assess_id_package_consistency


def _view() -> dict[str, object]:
    documents = [
        {
            "ordinal": 2,
            "membership_id": "membership-a",
            "membership_version": 4,
            "role": "support.aosr",
            "subject_kind": "generated_document_candidate",
            "subject_ref": "candidate-a",
            "copies": 1,
            "stage": "work_acceptance",
            "state": "generated_candidate",
        }
    ]
    return {
        "package": {"id_package_id": "package-independent", "version": 4},
        "registers": [
            {
                "register_candidate_id": "register-independent",
                "register_manifest": {
                    "package_id": "package-independent",
                    "package_version": 4,
                    "documents": documents,
                },
            }
        ],
        "memberships": [
            {
                "ordinal": 1,
                "membership_id": "register-membership",
                "version": 4,
                "role": "register",
                "state": "generated_candidate",
            },
            {
                "ordinal": 2,
                "membership_id": "membership-a",
                "version": 4,
                "role": "support.aosr",
                "subject_kind": "generated_document_candidate",
                "subject_ref": "candidate-a",
                "required_copy_count": 1,
                "stage": "work_acceptance",
                "state": "generated_candidate",
                "generation_run_id": "run-independent",
                "generated_candidate_id": "candidate-a",
                "object_reference": "derived/candidate-a.pdf",
                "bytes_digest": "sha256:" + "a" * 64,
                "job_state": "succeeded",
                "template_id": "template-independent",
                "template_version": "2.0.0",
                "template_qualification_state": "active",
                "template_official_status": "verified",
                "template_assurance_class": "production",
            },
        ],
        "field_resolutions": [
            {
                "generation_run_id": "run-independent",
                "field_key": "work_description",
                "state": "confirmed",
                "material": True,
                "evidence_link_id": "evidence-independent",
                "source_locator_id": "locator-independent",
            }
        ],
    }


def test_candidate_package_is_consistent_but_still_requires_review() -> None:
    result = assess_id_package_consistency(_view())

    assert result["status"] == "review_required"
    assert result["gaps"] == []
    assert result["summary"] == {
        "member_count": 1,
        "generated_candidate_count": 1,
        "finalized_count": 0,
        "incomplete_count": 0,
        "referenced_generation_run_count": 1,
    }
    assert all(check["outcome"] == "passed" for check in result["checks"])


def test_register_mismatch_and_missing_material_evidence_are_not_hidden() -> None:
    value = _view()
    registers = value["registers"]
    assert isinstance(registers, list)
    registers[0]["register_manifest"]["documents"][0]["subject_ref"] = "wrong-candidate"
    fields = value["field_resolutions"]
    assert isinstance(fields, list)
    fields[0]["evidence_link_id"] = None

    result = assess_id_package_consistency(value)

    assert result["status"] == "inconsistent"
    assert "ID_PACKAGE_REGISTER_MEMBERSHIP_MISMATCH" in result["gaps"]
    assert (
        "ID_MATERIAL_FIELD_EVIDENCE_INCOMPLETE:run-independent:work_description" in result["gaps"]
    )


def test_unformed_package_is_not_reported_as_complete() -> None:
    result = assess_id_package_consistency({"package": None})

    assert result["status"] == "not_formed"
    assert result["gaps"] == ["ID_PACKAGE_NOT_FORMED"]
