"""Deterministic local reconciliation contracts for offline Support facts."""

from __future__ import annotations

from .models import OfflineDisposition, OfflineFactEnvelope, OfflineReconciliation


class OfflineFactReconciler:
    """Idempotent reconciliation without last-write-wins or network authority."""

    def __init__(self) -> None:
        self._observations: dict[str, str] = {}

    def reconcile(self, envelope: OfflineFactEnvelope) -> OfflineReconciliation:
        key = str(envelope.observation_id)
        previous = self._observations.get(key)
        if previous is None:
            self._observations[key] = envelope.fingerprint
            return OfflineReconciliation(OfflineDisposition.ACCEPTED, envelope.fingerprint)
        if previous == envelope.fingerprint:
            return OfflineReconciliation(OfflineDisposition.DUPLICATE, previous)
        return OfflineReconciliation(
            OfflineDisposition.QUARANTINED,
            previous,
            tuple(sorted((previous, envelope.fingerprint))),
        )
