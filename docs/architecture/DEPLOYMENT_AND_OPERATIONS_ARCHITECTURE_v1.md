# Deployment and Operations Architecture v1

## Native MBP profile

The mandatory runtime is native macOS without Docker:

- signed/versioned application release and static frontend assets;
- launchd-managed Python API, document worker and model broker;
- PostgreSQL canonical platform/workspace metadata;
- durable content-addressed object/source/output plane;
- one-heavy-MLX-process lease/fence;
- structured local logs, health/metrics/traces and redaction;
- backup/restore, projection rebuild and release rollback commands.

Processes run under least privilege and do not daemonize themselves behind
launchd. Service health distinguishes dependency availability from product
readiness. A restarted worker resumes or reconciles durable jobs without manual
database edits.

king25/Ubuntu may use the protected network and typed API/UI with ordinary
authentication/authorization. It receives no database, object-plane or model
credentials and cannot become an implicit primary. VPS/external execution
remain separately authorized optional profiles.

## Release and recovery

Release artifacts are immutable, hashed and signed. Compatibility covers code,
database head, Contract Pack, frontend client and context/model profiles.
Activation is explicit after backup and health checks. The previous compatible
release remains available for rollback; migrations that cannot be safely
rolled back require forward recovery and a documented fence. Update metadata
must resist rollback/freeze and key-compromise risks.

## Acceptance

Fresh install, restart, crash, disk/DB/object outage, backup/restore, projection
rebuild, signed update, failed update rollback, uninstall/retention, protected
remote access and one-heavy-model enforcement must pass before TrialReady.
