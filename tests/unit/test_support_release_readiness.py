from __future__ import annotations

from asd_kontur.support.release_readiness import load_support_work_type_profiles


def test_support_qualification_profiles_report_real_repository_denominators() -> None:
    value = load_support_work_type_profiles()
    profiles = value["profiles"]

    assert {item["work_type_key"] for item in profiles} == {
        "concrete.slab.install",
        "earthworks",
        "reinforced-concrete",
        "pipeline-installation",
    }
    assert sum(bool(item["package_capable"]) for item in profiles) == 4
    assert sum(bool(item["isolated_qualification"]) for item in profiles) == 4
    assert sum(bool(item["browser_e2e"]) for item in profiles) == 1
    assert sum(bool(item["field_requirement_profile"]) for item in profiles) == 3
    assert all(item["blockers"] for item in profiles)
