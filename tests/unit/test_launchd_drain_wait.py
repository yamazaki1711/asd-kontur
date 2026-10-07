"""A service in SIGTERMed state is not yet safe to bootstrap again."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parents[2] / "tools/wait_launchd_service_stopped.py"
_SPEC = importlib.util.spec_from_file_location("wait_launchd_service_stopped", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
wait_until_removed = _MODULE.wait_until_removed


def test_waits_for_service_disappearance_after_sigtermed_interval() -> None:
    clock = [0.0]
    seen: list[str] = []

    def service_exists(name: str) -> bool:
        seen.append(name)
        return clock[0] < 18.0

    assert wait_until_removed(
        role="project-orchestrator",
        uid=501,
        timeout_seconds=30,
        interval_seconds=2,
        print_service=service_exists,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    assert clock[0] == 18.0
    assert set(seen) == {"gui/501/ru.asd-kontur.spine.project-orchestrator"}


def test_times_out_without_treating_sigtermed_as_removed() -> None:
    clock = [0.0]
    assert not wait_until_removed(
        role="project-orchestrator",
        uid=501,
        timeout_seconds=5,
        interval_seconds=2,
        print_service=lambda _: True,
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    assert clock[0] == 5.0
