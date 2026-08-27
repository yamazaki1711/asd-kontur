# FIELD-ANDROID-CLIENT-01 — registered technical debt

Status: `NOT_IMPLEMENTED`. Tracking: [GitHub issue #24](https://github.com/yamazaki1711/asd-kontur/issues/24).

This required Field/Offline capability is a secure, offline-first industrial
Android client for evidence collection in Support, Audit and Restoration. It is
not a reduced desktop UI and does not own a separate domain or knowledge model.

## Superseding legacy and authentication decision

- `legacy_decision = USE_AS_REFERENCE_ONLY`;
- `target_implementation = REIMPLEMENT_FROM_SEMANTICS`;
- `authentication_architecture = UNDECIDED`;
- a separate architecture/security ADR and threat model are mandatory before
  implementation.

The preserved requirement is rapid, unique and offline-capable resolution of a
concrete operator on an enrolled protected device. Device trust, operator
authentication, exact `OperatorAssignmentVersion`, personal session and evidence
attribution are separate controls. Name, organization, position, active role and
permissions come from the immutable assignment version; they are not encoded in
a PIN or selected from a mutable roster after login.

The future ADR compares at least personal PIN, NFC plus PIN, QR/smart-card plus
PIN, passkey/device credential and supplemental biometrics for shared and
personally assigned tablets in online and offline states. A fully managed tablet
with a device-bound hardware key, signed offline roster, NFC badge and personal
PIN is only a research candidate, not an accepted design.

Every future field action is attributed to stable operator, exact assignment,
device, session and workspace identities plus local/server time and monotonic
offline sequence. Historical authorship is immutable when a name, position,
organization or role later changes. PIN, if selected, would identify an operator
on a trusted device; it would not constitute a legal signature.

The retained domain scope includes photos, video, scans, notes, measurements,
coordinates, quantities, MTR batches, laboratory and geodetic results,
observations and remediation confirmations linked to assignments, checkpoints,
OKS locations and exact basis versions. Offline records have UUIDs, immutable
originals and visible pending/sent/conflict states; both conflict versions are
preserved. Local deletion after capture is forbidden, and encrypted cached
evidence may be purged only after acknowledged synchronization and retention
policy allow it.

The future client must use the shared Application API, workspace identities,
authorization, Document Registry, Evidence Ledger, durable jobs, ContextPack and
lifecycle/reset contracts. Original captures remain immutable and content
addressed; edits are derived artifacts with lineage. Synchronization is
idempotent, resumable, fenced, finite and concludes with an immutable server
receipt. Device time, location and signatures have explicit trust status rather
than automatic verification.

An approved threat model and comparative architecture decisions are mandatory
before implementation. No Android language/UI toolkit, MDM, device vendor,
distribution mechanism or local AI capability is selected by this record.

Historical `mac_asd` field/mobile materials will be inventoried by the future
field-client architecture task only as regression and domain-semantics evidence.
Their code, PIN scheme, UI, storage and synchronization architecture are
`USE_AS_REFERENCE_ONLY`; mechanical reuse is prohibited.

Its absence blocks the applicable field acceptance for Support, Audit and
Restoration and therefore blocks `ProductReady`. It does not expand
INDUSTRIAL-DOCUMENT-UNDERSTANDING-01 into mobile development.
