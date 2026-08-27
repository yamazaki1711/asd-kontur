"""Disposable PostgreSQL construction and deterministic inventory functions."""

from __future__ import annotations

import os
import subprocess
from argparse import Namespace
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from .models import IntegrityFailure, canonical_digest

DISPOSABLE_PREFIX = "asd_integrity_"


def _assert_disposable_name(database_name: str) -> None:
    if (
        not database_name.startswith(DISPOSABLE_PREFIX)
        or not database_name.replace("_", "").isalnum()
    ):
        raise IntegrityFailure(
            "UNSAFE_DATABASE_TARGET",
            f"database must use the {DISPOSABLE_PREFIX!r} prefix",
        )


def create_database(cluster_engine: Engine, database_name: str) -> None:
    _assert_disposable_name(database_name)
    with cluster_engine.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')


def drop_database(cluster_engine: Engine, database_name: str) -> None:
    _assert_disposable_name(database_name)
    with cluster_engine.connect() as connection:
        connection.exec_driver_sql(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')


def migrate(repository_root: Path, database_url: URL, revision: str) -> None:
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.cmd_opts = Namespace(
        x=[f"database_url={database_url.render_as_string(hide_password=False)}"]
    )
    if revision == "head":
        command.upgrade(configuration, revision)
    else:
        prior = os.environ.get("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE")
        os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = "1"
        try:
            command.downgrade(configuration, revision)
        finally:
            if prior is None:
                os.environ.pop("ASD_ALLOW_DESTRUCTIVE_DOWNGRADE", None)
            else:
                os.environ["ASD_ALLOW_DESTRUCTIVE_DOWNGRADE"] = prior


def restore_custom_dump(*, database_url: URL, dump_path: Path) -> None:
    if not dump_path.is_file():
        raise IntegrityFailure("BACKUP_OBJECT_UNAVAILABLE", "qualification backup is unavailable")
    command_line = [
        "pg_restore",
        "--host",
        database_url.host or "localhost",
        "--port",
        str(database_url.port or 5432),
        "--username",
        database_url.username or "",
        "--dbname",
        database_url.database or "",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        str(dump_path),
    ]
    environment = dict(os.environ)
    if database_url.password:
        environment["PGPASSWORD"] = database_url.password
    completed = subprocess.run(
        command_line,
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
        env=environment,
    )
    if completed.returncode:
        raise IntegrityFailure(
            "BACKUP_RESTORE_FAILED",
            "pg_restore did not complete",
            evidence={"returncode": completed.returncode},
        )


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def schema_inventory(engine: Engine) -> dict[str, Any]:
    queries = {
        "columns": """
            SELECT table_schema,table_name,column_name,data_type,
                   udt_schema,udt_name,is_nullable,column_default,identity_generation
            FROM information_schema.columns
            WHERE table_schema IN ('public','organization','workspace','platform',
                                   'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "constraints": """
            SELECT n.nspname,c.relname,k.conname,k.contype,pg_get_constraintdef(k.oid,true)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('public','organization','workspace','platform',
                                'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "indexes": """
            SELECT schemaname,tablename,indexname,indexdef
            FROM pg_indexes
            WHERE schemaname IN ('public','organization','workspace','platform',
                                 'projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "functions": """
            SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
                   pg_get_functiondef(p.oid)
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "triggers": """
            SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid,true)
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE NOT t.tgisinternal AND n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "policies": """
            SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check
            FROM pg_policies
            WHERE schemaname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2,3
        """,
        "rls": """
            SELECT n.nspname,c.relname,c.relrowsecurity,c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind='r' AND n.nspname IN
                  ('organization','workspace','platform','projection','audit','messaging')
            ORDER BY 1,2
        """,
    }
    inventory: dict[str, Any] = {}
    with engine.connect() as connection:
        for key, query in queries.items():
            inventory[key] = [_plain(tuple(row)) for row in connection.execute(sa.text(query))]
    return inventory


def schema_fingerprint(engine: Engine) -> str:
    return canonical_digest(schema_inventory(engine))


PLATFORM_MEMORY_SCHEMA_VERSION = "platform-memory-fingerprint-v2.1.0"

# These are canonical source/history relations.  A relation being empty is valid; a
# relation being absent is a schema defect and must never be normalized to an empty set.
PERMANENT_RELATIONS = (
    ("platform", "source_artifacts"),
    ("platform", "source_versions"),
    ("platform", "source_locators"),
    ("platform", "practice_guides"),
    ("platform", "practice_guide_editions"),
    ("platform", "practice_guide_edition_states"),
    ("platform", "practice_guide_edition_activation_decisions"),
    ("platform", "practice_guide_candidate_versions"),
    ("platform", "practice_guide_failed_candidate_versions"),
    ("platform", "practice_guide_validation_results"),
    ("platform", "practice_guide_verifications"),
    ("platform", "practice_guide_verification_selection_decisions"),
    ("platform", "practice_guide_ingestion_reconciliations"),
    ("platform", "practice_guide_page_manifests"),
    ("platform", "practice_guide_source_rows"),
    ("platform", "practice_guide_structural_units"),
    ("platform", "practice_guide_normative_reference_candidates"),
    ("platform", "practice_guide_normative_reference_resolutions"),
    ("platform", "practice_guide_ntd_relevance_assertions"),
    ("platform", "practice_guidance_units"),
    ("platform", "practice_guidance_evidence"),
    ("platform", "practice_guidance_coverage_manifests"),
    ("platform", "practice_guidance_gaps"),
    ("platform", "practice_guidance_conflicts"),
    ("platform", "practice_guidance_uncertainties"),
    ("platform", "practice_intelligence_construction_manifests"),
    # Pre-0018 immutable construction rows remain historical provenance.
    ("platform", "practice_intelligence_units"),
    ("platform", "practice_intelligence_sources"),
    ("platform", "practice_playbooks"),
    ("platform", "practice_playbook_members"),
    # 0018 normalized semantic identity/version/evidence layer.
    ("platform", "practice_intelligence_identities"),
    ("platform", "practice_intelligence_versions"),
    ("platform", "practice_intelligence_evidence_links"),
    ("platform", "practice_playbook_identities"),
    ("platform", "practice_playbook_versions_v2"),
    ("platform", "practice_playbook_version_members"),
    ("platform", "context_assembly_policies"),
    ("platform", "practice_intelligence_releases"),
    ("platform", "practice_intelligence_release_memberships"),
    ("platform", "practice_playbook_release_memberships"),
    ("platform", "practice_intelligence_release_activation_decisions"),
    ("platform", "practice_intelligence_reconciliation_decisions"),
    ("platform", "platform_memory_fingerprint_specifications"),
    ("platform", "practice_guide_normative_references"),
    ("platform", "practice_guide_ntd_resolution_decisions"),
    ("platform", "practice_ntd_alignments"),
    ("platform", "normative_documents"),
    ("platform", "normative_editions"),
    ("platform", "normative_artifacts"),
    ("platform", "normative_edition_relationships"),
    ("platform", "normative_edition_states"),
    ("platform", "normative_references"),
    ("platform", "normative_provision_candidates"),
    ("platform", "normative_provision_versions"),
    ("platform", "normative_activation_decisions"),
    ("platform", "normative_applicability_decisions"),
    ("platform", "normative_seed_outcomes"),
    ("platform", "normative_conflicts"),
    ("platform", "ntd_gaps"),
    ("platform", "ntd_conflicts"),
    ("platform", "rule_versions"),
    ("platform", "rule_version_states"),
    ("platform", "rule_set_versions"),
    ("platform", "rule_set_memberships"),
    ("platform", "rules"),
    ("platform", "rule_evidence"),
    ("platform", "rule_reviews"),
    ("platform", "rule_approvals"),
    ("platform", "normative_rule_candidates"),
    ("platform", "normative_rule_qualification_decisions"),
    ("platform", "normative_rule_activation_outcomes"),
)

NON_SEMANTIC_COLUMNS = frozenset(
    {
        "created_at",
        "recorded_at",
        "constructed_at",
        "published_at",
        "built_at",
        "rebuilt_at",
        "updated_at",
        "generated_at",
        "completed_at",
        "search_vector",
    }
)

RELATION_NON_SEMANTIC_COLUMNS: dict[tuple[str, str], frozenset[str]] = {
    ("platform", "practice_intelligence_release_memberships"): frozenset({"member_sequence"}),
    ("platform", "practice_playbook_release_memberships"): frozenset({"member_sequence"}),
}

REQUIRED_SEMANTIC_COLUMNS: dict[tuple[str, str], frozenset[str]] = {
    ("platform", "source_versions"): frozenset(
        {"source_version_id", "source_artifact_id", "object_id", "content_digest"}
    ),
    ("platform", "source_locators"): frozenset(
        {"source_locator_id", "source_version_id", "locator_key", "locator_value"}
    ),
    ("platform", "practice_guide_editions"): frozenset(
        {"practice_guide_edition_id", "practice_guide_id", "source_version_id"}
    ),
    ("platform", "practice_guidance_units"): frozenset(
        {"guidance_unit_id", "version", "guidance_candidate_id", "candidate_version"}
    ),
    ("platform", "practice_guidance_evidence"): frozenset(
        {"guidance_unit_id", "guidance_unit_version", "source_version_id", "fragment_digest"}
    ),
    ("platform", "practice_intelligence_identities"): frozenset(
        {
            "intelligence_identity_id",
            "practice_guide_edition_id",
            "evidence_scope_digest",
            "normalized_semantic_digest",
        }
    ),
    ("platform", "practice_intelligence_versions"): frozenset(
        {"intelligence_identity_id", "version", "canonical_payload", "semantic_fingerprint"}
    ),
    ("platform", "practice_intelligence_evidence_links"): frozenset(
        {
            "evidence_link_id",
            "intelligence_identity_id",
            "intelligence_version",
            "source_version_id",
            "source_locator_id",
            "guidance_candidate_id",
        }
    ),
    ("platform", "practice_intelligence_releases"): frozenset(
        {
            "release_id",
            "version",
            "practice_guide_edition_id",
            "context_assembly_policy_id",
            "canonical_semantic_fingerprint",
        }
    ),
    ("platform", "practice_intelligence_release_activation_decisions"): frozenset(
        {"practice_guide_id", "selected_release_id", "selected_release_version"}
    ),
    ("platform", "context_assembly_policies"): frozenset(
        {"policy_id", "version", "practice_guide_edition_id", "policy_fingerprint", "state"}
    ),
    ("platform", "normative_editions"): frozenset(
        {"normative_edition_id", "normative_document_id", "source_version_id"}
    ),
    ("platform", "normative_provision_versions"): frozenset(
        {"normative_provision_id", "version", "normative_edition_id", "semantic_fingerprint"}
    ),
    ("platform", "rule_versions"): frozenset(
        {"rule_version_id", "rule_id", "version", "integrity_digest"}
    ),
    ("platform", "normative_rule_candidates"): frozenset(
        {
            "normative_rule_candidate_id",
            "version",
            "normative_edition_id",
            "source_version_id",
            "normative_provision_id",
            "normative_provision_version",
            "source_locator_id",
            "semantic_fingerprint",
        }
    ),
    ("platform", "normative_rule_qualification_decisions"): frozenset(
        {
            "qualification_decision_id",
            "normative_rule_candidate_id",
            "status",
            "decision_fingerprint",
        }
    ),
    ("platform", "normative_rule_activation_outcomes"): frozenset(
        {
            "rule_activation_outcome_id",
            "normative_rule_candidate_id",
            "status",
            "reason_code",
            "decision_fingerprint",
        }
    ),
}

EXCLUDED_MEMORY_RELATIONS = {
    "workspace-specific-data": "workspace schemas are outside permanent platform memory",
    "AI request/response artifacts": "processing receipts do not define canonical semantics",
    "platform.practice_guide_ingestion_runs": "runtime attempt state",
    "platform.practice_guide_ingestion_run_states": "runtime attempt state",
    "platform.practice_guide_page_terminal_receipts": "processing receipt metadata",
    "platform.practice_memory_backup_manifests": "backup operation receipt",
    "platform.ntd_backup_manifests": "backup operation receipt",
    "platform.ntd_catalogue_query_receipts": "acquisition operation receipt",
    "platform.ntd_parse_receipts": "parser operation receipt",
    "platform.system_integrity_decisions": "qualification status, not knowledge semantics",
    "platform.platform_memory_qualification_decisions": (
        "qualification result references fingerprints and is excluded to avoid recursion"
    ),
    "projection rows": "FTS/vector/graph/runtime projection content is rebuildable",
}

REBUILDABLE_PROJECTION_RELATIONS = (
    ("projection", "practice_guidance_lexical_versions"),
    ("projection", "practice_guidance_lexical_entries"),
    ("projection", "practice_intelligence_lexical_versions"),
    ("projection", "practice_intelligence_lexical_entries"),
    ("projection", "ntd_lexical_versions"),
    ("projection", "ntd_lexical_entries"),
)

# Backward-compatible name used by lifecycle checks.  It now contains only actual
# platform relation names and is never used as an optional inventory.
PERMANENT_TABLES = tuple(
    relation for schema, relation in PERMANENT_RELATIONS if schema == "platform"
)


def memory_relation_inventory(
    engine: Engine,
    relations: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    inspector = sa.inspect(engine)
    relation_list = tuple(relations)
    existing_by_schema = {
        schema: set(inspector.get_table_names(schema=schema))
        for schema in {schema for schema, _ in relation_list}
    }
    missing = [
        f"{schema}.{table}"
        for schema, table in relation_list
        if table not in existing_by_schema[schema]
    ]
    if missing:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_SCHEMA_INCOMPLETE",
            "a required canonical memory relation is absent",
            evidence={"missing_relations": missing},
        )

    inventory: dict[str, Any] = {
        "schema_version": PLATFORM_MEMORY_SCHEMA_VERSION,
        "canonicalization": {
            "row_order": "canonical_digest",
            "value_encoding": "typed-json-v1",
            "non_semantic_columns": sorted(NON_SEMANTIC_COLUMNS),
        },
        "components": {},
    }
    with engine.connect() as connection:
        for schema, table in relation_list:
            columns = [str(item["name"]) for item in inspector.get_columns(table, schema=schema)]
            if not columns:
                raise IntegrityFailure(
                    "PLATFORM_MEMORY_COLUMNS_UNAVAILABLE",
                    "canonical memory columns cannot be inspected",
                    evidence={"relation": f"{schema}.{table}"},
                )
            missing_columns = sorted(
                REQUIRED_SEMANTIC_COLUMNS.get((schema, table), frozenset()) - set(columns)
            )
            if missing_columns:
                raise IntegrityFailure(
                    "PLATFORM_MEMORY_SCHEMA_INCOMPLETE",
                    "a required canonical memory column is absent",
                    evidence={
                        "relation": f"{schema}.{table}",
                        "missing_columns": missing_columns,
                    },
                )
            excluded = NON_SEMANTIC_COLUMNS | RELATION_NON_SEMANTIC_COLUMNS.get(
                (schema, table), frozenset()
            )
            selected = sorted(column for column in columns if column not in excluded)
            if not selected:
                raise IntegrityFailure(
                    "PLATFORM_MEMORY_SEMANTIC_COLUMNS_EMPTY",
                    "canonical memory relation has no semantic columns",
                    evidence={"relation": f"{schema}.{table}"},
                )
            quoted = ",".join(f'"{column}"' for column in selected)
            rows = [
                _plain(dict(row._mapping))
                for row in connection.execute(sa.text(f'SELECT {quoted} FROM "{schema}"."{table}"'))
            ]
            rows.sort(key=canonical_digest)
            component = {
                "included_columns": selected,
                "excluded_columns": sorted(set(columns) - set(selected)),
                "row_count": len(rows),
                "rows": rows,
            }
            component["fingerprint"] = canonical_digest(component)
            inventory["components"][f"{schema}.{table}"] = component
    return inventory


def platform_memory_inventory(engine: Engine) -> dict[str, Any]:
    """Return fail-closed all-history canonical and projection lineage."""

    inventory = memory_relation_inventory(engine, PERMANENT_RELATIONS)
    inspector = sa.inspect(engine)
    projection_bindings: list[dict[str, Any]] = []
    for schema, table in REBUILDABLE_PROJECTION_RELATIONS:
        if table not in set(inspector.get_table_names(schema=schema)):
            raise IntegrityFailure(
                "PLATFORM_MEMORY_SCHEMA_INCOMPLETE",
                "a required rebuildable projection relation is absent",
                evidence={"missing_relations": [f"{schema}.{table}"]},
            )
        columns = sorted(
            [
                {
                    "name": str(item["name"]),
                    "type": str(item["type"]),
                    "nullable": bool(item["nullable"]),
                }
                for item in inspector.get_columns(table, schema=schema)
            ],
            key=canonical_digest,
        )
        projection_bindings.append(
            {
                "relation": f"{schema}.{table}",
                "columns": columns,
            }
        )
    inventory["rebuildable_projection_schema_binding"] = {
        "binding_version": "rebuildable-projection-schema-binding-v1.0.0",
        "relations": projection_bindings,
    }
    with engine.connect() as connection:
        projection_versions = [
            _plain(dict(row._mapping))
            for row in connection.execute(
                sa.text(
                    "SELECT release_id,release_version,projection_kind,projection_version,"
                    "source_semantic_fingerprint FROM "
                    "projection.practice_intelligence_projection_manifests"
                )
            )
        ]
    projection_versions.sort(key=canonical_digest)
    inventory["rebuildable_projection_version_binding"] = projection_versions
    inventory["excluded_components"] = EXCLUDED_MEMORY_RELATIONS
    return inventory


def platform_memory_fingerprint(engine: Engine) -> str:
    """All-history platform-memory fingerprint (legacy public API)."""

    return canonical_digest(platform_memory_inventory(engine))


def _active_release_binding(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                sa.text(
                    """
                    WITH selected AS (
                      SELECT decision.*,
                             row_number() OVER (
                               PARTITION BY practice_guide_id ORDER BY version DESC
                             ) AS selected_rank
                      FROM platform.practice_intelligence_release_activation_decisions decision
                    )
                    SELECT selected.practice_guide_id,
                           selected.release_activation_decision_id,
                           selected.version AS release_activation_version,
                           selected.selected_release_id,
                           selected.selected_release_version,
                           selected.decision_fingerprint AS release_activation_fingerprint,
                           release.construction_manifest_id,
                           release.practice_guide_edition_id,
                           release.source_version_id,
                           release.context_assembly_policy_id,
                           release.context_assembly_policy_version,
                           release.canonical_semantic_fingerprint,
                           release.publication_status,
                           policy.policy_fingerprint,
                           policy.state AS policy_state,
                           construction.construction_fingerprint,
                           construction.construction_profile_version,
                           edition_activation.selected_edition_id,
                           edition_activation.decision_fingerprint
                             AS edition_activation_fingerprint,
                           lexical.lexical_version_id,
                           lexical.projection_contract_version,
                           lexical.source_fingerprint AS projection_source_fingerprint,
                           lexical.state AS projection_state
                    FROM selected
                    JOIN platform.practice_intelligence_releases release
                      ON release.release_id=selected.selected_release_id
                     AND release.version=selected.selected_release_version
                    JOIN platform.context_assembly_policies policy
                      ON policy.policy_id=release.context_assembly_policy_id
                     AND policy.version=release.context_assembly_policy_version
                    JOIN platform.practice_intelligence_construction_manifests construction
                      ON construction.construction_manifest_id=release.construction_manifest_id
                    JOIN LATERAL (
                      SELECT activation.selected_edition_id,activation.decision_fingerprint
                      FROM platform.practice_guide_edition_activation_decisions activation
                      WHERE activation.practice_guide_id=selected.practice_guide_id
                      ORDER BY activation.version DESC LIMIT 1
                    ) edition_activation ON true
                    JOIN LATERAL (
                      SELECT candidate.lexical_version_id,
                             candidate.projection_contract_version,
                             candidate.source_fingerprint,candidate.state
                      FROM projection.practice_intelligence_lexical_versions candidate
                      WHERE candidate.construction_manifest_id=release.construction_manifest_id
                      ORDER BY candidate.built_at DESC NULLS LAST,
                               candidate.lexical_version_id DESC
                      LIMIT 1
                    ) lexical ON true
                    WHERE selected.selected_rank=1
                    ORDER BY selected.practice_guide_id
                    """
                )
            )
        )
        guide_count = int(
            connection.scalar(
                sa.text(
                    "SELECT count(DISTINCT edition.practice_guide_id) FROM "
                    "platform.practice_intelligence_releases release JOIN "
                    "platform.practice_guide_editions edition ON "
                    "edition.practice_guide_edition_id=release.practice_guide_edition_id"
                )
            )
            or 0
        )
        if len(rows) != guide_count or guide_count == 0:
            raise IntegrityFailure(
                "ACTIVE_RELEASE_SELECTION_INCOMPLETE",
                "every PracticeGuide must have exactly one selected release",
                evidence={"practice_guide_count": guide_count, "binding_count": len(rows)},
            )
        bindings = [_plain(dict(row._mapping)) for row in rows]
        for binding in bindings:
            if binding["policy_state"] != "active":
                raise IntegrityFailure(
                    "ACTIVE_CONTEXT_POLICY_INVALID",
                    "the selected release is not bound to an active policy",
                    evidence={"binding": binding},
                )
            if binding["projection_state"] != "ready":
                raise IntegrityFailure(
                    "ACTIVE_PROJECTION_BINDING_INVALID",
                    "the selected release has no ready retrieval projection",
                    evidence={"binding": binding},
                )
            if binding["selected_edition_id"] != binding["practice_guide_edition_id"]:
                raise IntegrityFailure(
                    "ACTIVE_EDITION_RELEASE_MISMATCH",
                    "the selected edition and selected release disagree",
                    evidence={"binding": binding},
                )
            intelligence_members = int(
                connection.scalar(
                    sa.text(
                        """
                        SELECT count(*)
                        FROM platform.practice_intelligence_release_memberships
                        WHERE release_id=:release_id AND release_version=:release_version
                        """
                    ),
                    {
                        "release_id": binding["selected_release_id"],
                        "release_version": binding["selected_release_version"],
                    },
                )
                or 0
            )
            if intelligence_members == 0:
                raise IntegrityFailure(
                    "ACTIVE_RELEASE_MEMBERSHIP_EMPTY",
                    "the selected release has no explicit intelligence membership",
                    evidence={"binding": binding},
                )
            binding["intelligence_membership_count"] = intelligence_members
            binding["playbook_membership_count"] = int(
                connection.scalar(
                    sa.text(
                        """
                        SELECT count(*)
                        FROM platform.practice_playbook_release_memberships
                        WHERE release_id=:release_id AND release_version=:release_version
                        """
                    ),
                    {
                        "release_id": binding["selected_release_id"],
                        "release_version": binding["selected_release_version"],
                    },
                )
                or 0
            )
    return {"schema_version": PLATFORM_MEMORY_SCHEMA_VERSION, "bindings": bindings}


def active_release_semantic_inventory(engine: Engine) -> dict[str, Any]:
    binding = _active_release_binding(engine)
    memberships: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    playbooks: list[dict[str, Any]] = []
    with engine.connect() as connection:
        for selected in binding["bindings"]:
            parameters = {
                "release_id": selected["selected_release_id"],
                "release_version": selected["selected_release_version"],
            }
            memberships.extend(
                _plain(dict(row._mapping))
                for row in connection.execute(
                    sa.text(
                        """
                        SELECT membership.release_id,membership.release_version,
                               membership.member_sequence,
                               membership.intelligence_identity_id,
                               membership.intelligence_version,
                               membership.membership_fingerprint,
                               identity.normalized_semantic_digest,
                               version.practice_guide_edition_id,
                               version.canonical_payload,version.semantic_fingerprint
                        FROM platform.practice_intelligence_release_memberships membership
                        JOIN platform.practice_intelligence_identities identity USING (
                          intelligence_identity_id
                        )
                        JOIN platform.practice_intelligence_versions version
                          ON version.intelligence_identity_id=membership.intelligence_identity_id
                         AND version.version=membership.intelligence_version
                        WHERE membership.release_id=:release_id
                          AND membership.release_version=:release_version
                        """
                    ),
                    parameters,
                )
            )
            evidence.extend(
                _plain(dict(row._mapping))
                for row in connection.execute(
                    sa.text(
                        """
                        SELECT link.evidence_link_id,link.intelligence_identity_id,
                               link.intelligence_version,link.source_guidance_unit_id,
                               link.source_guidance_unit_version,link.source_version_id,
                               link.source_locator_id,link.guidance_candidate_id,
                               link.candidate_version,link.evidence_digest,
                               link.extraction_verification_receipt
                        FROM platform.practice_intelligence_evidence_links link
                        JOIN platform.practice_intelligence_release_memberships membership
                          ON membership.intelligence_identity_id=link.intelligence_identity_id
                         AND membership.intelligence_version=link.intelligence_version
                        WHERE membership.release_id=:release_id
                          AND membership.release_version=:release_version
                        """
                    ),
                    parameters,
                )
            )
            playbooks.extend(
                _plain(dict(row._mapping))
                for row in connection.execute(
                    sa.text(
                        """
                        SELECT membership.release_id,membership.release_version,
                               membership.member_sequence,membership.playbook_identity_id,
                               membership.playbook_version,membership.membership_fingerprint,
                               identity.normalized_semantic_digest,
                               version.canonical_payload,version.semantic_fingerprint
                        FROM platform.practice_playbook_release_memberships membership
                        JOIN platform.practice_playbook_identities identity USING (
                          playbook_identity_id
                        )
                        JOIN platform.practice_playbook_versions_v2 version
                          ON version.playbook_identity_id=membership.playbook_identity_id
                         AND version.version=membership.playbook_version
                        WHERE membership.release_id=:release_id
                          AND membership.release_version=:release_version
                        """
                    ),
                    parameters,
                )
            )
    for rows in (memberships, evidence, playbooks):
        rows.sort(key=canonical_digest)
    return {
        "schema_version": PLATFORM_MEMORY_SCHEMA_VERSION,
        "release_binding": binding,
        "intelligence_versions": memberships,
        "evidence_links": evidence,
        "playbook_versions": playbooks,
    }


def active_release_semantic_fingerprint(engine: Engine) -> str:
    return canonical_digest(active_release_semantic_inventory(engine))


def active_context_binding_inventory(engine: Engine) -> dict[str, Any]:
    return _active_release_binding(engine)


def active_context_binding_fingerprint(engine: Engine) -> str:
    return canonical_digest(active_context_binding_inventory(engine))


def active_semantic_duplicate_inventory(engine: Engine) -> list[dict[str, Any]]:
    """Return semantic digests represented more than once in the selected release."""

    binding = _active_release_binding(engine)
    duplicates: list[dict[str, Any]] = []
    with engine.connect() as connection:
        for selected in binding["bindings"]:
            rows = connection.execute(
                sa.text(
                    """
                    SELECT identity.normalized_semantic_digest,count(*) AS member_count,
                           array_agg(membership.intelligence_identity_id::text
                                     ORDER BY membership.intelligence_identity_id::text)
                             AS intelligence_identity_ids
                    FROM platform.practice_intelligence_release_memberships membership
                    JOIN platform.practice_intelligence_identities identity USING (
                      intelligence_identity_id
                    )
                    WHERE membership.release_id=:release_id
                      AND membership.release_version=:release_version
                    GROUP BY identity.normalized_semantic_digest
                    HAVING count(*)>1
                    ORDER BY identity.normalized_semantic_digest
                    """
                ),
                {
                    "release_id": selected["selected_release_id"],
                    "release_version": selected["selected_release_version"],
                },
            )
            duplicates.extend(_plain(dict(row._mapping)) for row in rows)
    return duplicates


def proven_duplicate_evidence_inventory(engine: Engine) -> list[dict[str, Any]]:
    """Locate exact duplicate occurrences reconciled under the evidence-bound contract."""

    expected = {
        ("visual_completion_example", (309,)),
        ("attention_point", (309,)),
    }
    binding = _active_release_binding(engine)
    if len(binding["bindings"]) != 1:
        raise IntegrityFailure(
            "DUPLICATE_REGRESSION_SCOPE_INVALID",
            "the bounded regression requires one selected Practice Guide release",
        )
    selected = binding["bindings"][0]
    with engine.connect() as connection:
        rows = [
            _plain(dict(row._mapping))
            for row in connection.execute(
                sa.text(
                    """
                    SELECT identity.intelligence_identity_id,identity.typed_kind,
                           count(*) AS evidence_link_count,
                           array_agg(DISTINCT
                             regexp_replace(locator.locator_key,
                               '^page:([0-9]+):.*$','\\1')::integer
                             ORDER BY regexp_replace(locator.locator_key,
                               '^page:([0-9]+):.*$','\\1')::integer) AS pages
                    FROM platform.practice_intelligence_release_memberships membership
                    JOIN platform.practice_intelligence_identities identity USING (
                      intelligence_identity_id
                    )
                    JOIN platform.practice_intelligence_evidence_links evidence
                      ON evidence.intelligence_identity_id=membership.intelligence_identity_id
                     AND evidence.intelligence_version=membership.intelligence_version
                    JOIN platform.source_locators locator
                      ON locator.source_locator_id=evidence.source_locator_id
                    WHERE membership.release_id=:release
                      AND membership.release_version=:release_version
                    GROUP BY identity.intelligence_identity_id,identity.typed_kind
                    HAVING count(*)>=2
                    ORDER BY identity.typed_kind,identity.intelligence_identity_id
                    """
                ),
                {
                    "release": selected["selected_release_id"],
                    "release_version": selected["selected_release_version"],
                },
            )
        ]
    matched = [
        row
        for row in rows
        if (str(row["typed_kind"]), tuple(int(page) for page in row["pages"])) in expected
    ]
    matched_keys = {
        (str(row["typed_kind"]), tuple(int(page) for page in row["pages"])) for row in matched
    }
    if matched_keys != expected or len(matched) != 2:
        raise IntegrityFailure(
            "SEMANTIC_DUPLICATE_REGRESSION_MISMATCH",
            "the two exact duplicate groups lost evidence lineage or changed scope",
            evidence={"expected": sorted(expected), "matched": matched},
        )
    return matched


def platform_memory_counts(engine: Engine) -> dict[str, int]:
    binding = _active_release_binding(engine)
    if len(binding["bindings"]) != 1:
        raise IntegrityFailure(
            "MULTIPLE_PRACTICE_GUIDE_COUNTING_SCOPE_UNSUPPORTED",
            "counter contract currently requires exactly one bounded PracticeGuide",
        )
    selected = binding["bindings"][0]
    parameters = {
        "release_id": selected["selected_release_id"],
        "release_version": selected["selected_release_version"],
        "construction_manifest_id": selected["construction_manifest_id"],
    }
    with engine.connect() as connection:

        def scalar(query: str) -> int:
            return int(connection.scalar(sa.text(query), parameters) or 0)

        active_intelligence = scalar(
            "SELECT count(*) FROM platform.practice_intelligence_release_memberships "
            "WHERE release_id=:release_id AND release_version=:release_version"
        )
        historical_intelligence = scalar(
            "SELECT count(*) FROM platform.practice_intelligence_units "
            "WHERE construction_manifest_id<>:construction_manifest_id"
        )
        active_playbooks = scalar(
            "SELECT count(*) FROM platform.practice_playbook_release_memberships "
            "WHERE release_id=:release_id AND release_version=:release_version"
        )
        historical_playbooks = scalar(
            "SELECT count(*) FROM platform.practice_playbooks "
            "WHERE construction_manifest_id<>:construction_manifest_id"
        )
        active_gaps = scalar(
            """
            SELECT count(*) FROM platform.practice_guidance_gaps gap
            JOIN platform.practice_intelligence_construction_manifests construction
              ON construction.coverage_manifest_id=gap.coverage_manifest_id
            WHERE construction.construction_manifest_id=:construction_manifest_id
            """
        )
        logical_gaps = scalar(
            """
            SELECT count(*) FROM (
              SELECT DISTINCT source_version_id,page_number,guidance_candidate_id,
                              candidate_version,gap_code,terminal_state,topic,
                              document_or_form_type,field_or_element
              FROM platform.practice_guidance_gaps
            ) logical_gap
            """
        )
        counts = {
            "source_guidance_identity_count": scalar(
                "SELECT count(DISTINCT guidance_unit_id) FROM platform.practice_guidance_units"
            ),
            "practice_intelligence_identity_count": scalar(
                "SELECT count(*) FROM platform.practice_intelligence_identities"
            ),
            "practice_intelligence_version_row_count": (
                active_intelligence + historical_intelligence
            ),
            "active_release_intelligence_version_count": active_intelligence,
            "historical_intelligence_version_count": historical_intelligence,
            "playbook_identity_count": scalar(
                "SELECT count(*) FROM platform.practice_playbook_identities"
            ),
            "playbook_version_row_count": active_playbooks + historical_playbooks,
            "active_release_playbook_count": active_playbooks,
            "historical_playbook_count": historical_playbooks,
            "logical_gap_identity_count": logical_gaps,
            "active_gap_identity_count": active_gaps,
            "closed_gap_identity_count": logical_gaps - active_gaps,
            "gap_snapshot_row_count": scalar(
                "SELECT count(*) FROM platform.practice_guidance_gaps"
            ),
            "conflict_identity_count": scalar(
                "SELECT count(DISTINCT guidance_conflict_id) "
                "FROM platform.practice_guidance_conflicts"
            ),
            "quarantined_candidate_identity_count": scalar(
                """
                SELECT count(DISTINCT (guidance_candidate_id,candidate_version))
                FROM platform.practice_guidance_conflicts
                WHERE guidance_unit_id IS NULL AND state='open'
                """
            ),
            "rule_version_count": scalar("SELECT count(*) FROM platform.rule_versions"),
        }
    if counts["closed_gap_identity_count"] < 0:
        raise IntegrityFailure(
            "GAP_COUNT_INVARIANT_FAILED",
            "active logical gaps exceed all logical gap identities",
            evidence={"counts": counts},
        )
    if (
        counts["practice_intelligence_version_row_count"]
        != counts["active_release_intelligence_version_count"]
        + counts["historical_intelligence_version_count"]
        or counts["playbook_version_row_count"]
        != counts["active_release_playbook_count"] + counts["historical_playbook_count"]
        or counts["logical_gap_identity_count"]
        != counts["active_gap_identity_count"] + counts["closed_gap_identity_count"]
    ):
        raise IntegrityFailure(
            "PLATFORM_MEMORY_COUNT_INVARIANT_FAILED",
            "explicit platform-memory denominators do not reconcile",
            evidence={"counts": counts},
        )
    return counts


def assert_no_workspace_ownership(engine: Engine) -> None:
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names(schema="platform"))
    missing = sorted(set(PERMANENT_TABLES) - existing)
    if missing:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_SCHEMA_INCOMPLETE",
            "workspace-ownership validation cannot omit canonical relations",
            evidence={"missing_relations": [f"platform.{table}" for table in missing]},
        )
    violations: list[str] = []
    for table in PERMANENT_TABLES:
        columns = {item["name"] for item in inspector.get_columns(table, schema="platform")}
        if "workspace_id" in columns or "organization_id" in columns:
            violations.append(table)
    if violations:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_WORKSPACE_OWNED",
            "permanent platform memory contains workspace ownership columns",
            evidence={"tables": violations},
        )


def assert_expected_counts(actual: dict[str, int], expected: dict[str, int]) -> None:
    differences = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if differences:
        raise IntegrityFailure(
            "PLATFORM_MEMORY_COUNT_MISMATCH",
            "restored qualification snapshot counts differ",
            evidence={"differences": differences},
        )


def duplicate_identity_inventory(engine: Engine) -> dict[str, list[tuple[Any, ...]]]:
    checks = {
        "migration_revisions": (
            "SELECT version_num,count(*) FROM alembic_version GROUP BY 1 HAVING count(*)>1"
        ),
        "source_versions": (
            "SELECT source_version_id,count(*) FROM platform.source_versions "
            "GROUP BY 1 HAVING count(*)>1"
        ),
        "practice_editions": (
            "SELECT practice_guide_edition_id,count(*) FROM platform.practice_guide_editions "
            "GROUP BY 1 HAVING count(*)>1"
        ),
    }
    output: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as connection:
        for key, query in checks.items():
            output[key] = [tuple(row) for row in connection.execute(sa.text(query))]
    return output


def assert_no_partial_state(engine: Engine, table_names: Iterable[str]) -> None:
    inspector = sa.inspect(engine)
    workspace_tables = set(inspector.get_table_names(schema="workspace"))
    missing = sorted(set(table_names) - workspace_tables)
    if missing:
        raise IntegrityFailure(
            "PARTIAL_SCHEMA_STATE",
            "expected head tables are missing",
            evidence={"missing": missing},
        )
