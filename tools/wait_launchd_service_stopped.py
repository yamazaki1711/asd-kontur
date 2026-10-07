"""Wait for a booted-out ASD-KONTUR role to disappear before replacement.

launchctl may report a service as SIGTERMed for several seconds after bootout.
Bootstrapping its replacement during that interval fails with error 5.
This command is read-only; it neither stops nor starts a service.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Callable

_ROLES = frozenset({"api", "worker", "project-orchestrator", "assistant-worker"})


def wait_until_removed(
    *,
    role: str,
    uid: int,
    timeout_seconds: float = 45.0,
    interval_seconds: float = 1.0,
    print_service: Callable[[str], bool],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Return false at the deadline; never interpret SIGTERMed as removed."""

    if role not in _ROLES or uid < 0 or timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("launchd_wait_arguments_invalid")
    service = f"gui/{uid}/ru.asd-kontur.spine.{role}"
    deadline = monotonic() + timeout_seconds
    while print_service(service):
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        sleep(min(interval_seconds, remaining))
    return True


def _service_exists(service: str) -> bool:
    result = subprocess.run(
        ["launchctl", "print", service],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=sorted(_ROLES), required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    stopped = wait_until_removed(
        role=args.role,
        uid=args.uid,
        timeout_seconds=args.timeout_seconds,
        print_service=_service_exists,
    )
    print(f"{'PASS' if stopped else 'FAIL'} {args.role} removed from launchd domain")
    return 0 if stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
