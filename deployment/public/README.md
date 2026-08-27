# Public deployment contour

These versioned files describe the four-surface public contour. Runtime
credentials, certificates, generated launchd plists, database data, object
payloads and receipts stay outside Git.

- `asd-kontur.ru`: static company website from `website/`;
- `app.asd-kontur.ru`: reverse proxy to the MBP authoritative primary;
- `bi.asd-kontur.ru`: existing BI plus isolated Levashovo archive;
- `tm.asd-kontur.ru`: deliberately absent from this directory and unchanged.

The app upstream binds only to VPS loopback port `18765`, supplied by the
supervised MBP reverse SSH ingress. A systemd socket proxy exposes it only on
the Docker bridge at `172.18.0.1:18766` for the nginx container. A failed ingress returns the typed
`authoritative_primary_unavailable` state and never falls back to legacy data.
