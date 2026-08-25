"""Run the exact pages 15-19 guide manifest and bounded official resolution."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.ntd.commands import persist_terminal_gap_report
from asd_kontur.ntd.manifest import build_seed_manifest
from asd_kontur.ntd.minstroy import MinstroyCatalogueClient, UrllibOfficialTransport
from asd_kontur.ntd.postgres import NtdRepository
from asd_kontur.ntd.resolution import resolve_seed_manifest
from asd_kontur.practice_guidance.native_layout import extract_native_page_layouts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--guide-pdf", type=Path, required=True)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--practice-guide-edition-id", type=UUID, required=True)
    parser.add_argument("--source-version-id", type=UUID, required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    args = parser.parse_args()
    if not args.staging_dir.is_absolute() or not args.staging_dir.is_dir():
        raise ValueError("A pre-created absolute staging directory is required")
    manifest = build_seed_manifest(
        practice_guide_edition_id=args.practice_guide_edition_id,
        source_version_id=args.source_version_id,
        layouts=extract_native_page_layouts(args.guide_pdf, first_page=15, last_page=19),
    )
    report = resolve_seed_manifest(
        MinstroyCatalogueClient(
            UrllibOfficialTransport(
                timeout_seconds=args.timeout_seconds,
                max_attempts=1,
                min_interval_seconds=0.5,
            ),
            max_search_pages=1,
        ),
        manifest,
    )
    manifest_path = args.staging_dir / "practice-guide-ntd-seed-manifest-v0.1.json"
    report_path = args.staging_dir / "official-resolution-report-v0.1.json"
    manifest_path.write_text(
        json.dumps(manifest.as_receipt(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report.safe_receipt(), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)
    report_path.chmod(0o600)
    gap_count = decision_count = 0
    if args.database_url:
        engine = sa.create_engine(args.database_url)
        try:
            gap_count, decision_count = persist_terminal_gap_report(
                NtdRepository(engine),
                manifest=manifest,
                report=report,
                created_by_identity_id="identity.owner-ntd-seed-01",
                recorded_at=datetime.now(UTC),
            )
        finally:
            engine.dispose()
    summary = {
        "manifest_fingerprint": manifest.fingerprint,
        "raw_mentions": manifest.raw_mention_count,
        "identities": manifest.identity_count,
        "terminal_outcomes": report.terminal_count,
        "terminal_status_counts": {
            status: sum(item.terminal_status.value == status for item in report.identities)
            for status in sorted({item.terminal_status.value for item in report.identities})
        },
        "gap_count": gap_count,
        "reference_resolution_decisions": decision_count,
        "report_fingerprint": report.report_fingerprint,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
