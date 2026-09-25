#!/usr/bin/env python3
"""Run the fixed-denominator consultant quality matrix against real local Qwen.

The tool creates ordinary durable conversations and turns in an explicitly
supplied qualification database.  It never calls Harness profiles and never
writes its runtime receipt into Git.
"""

# ruff: noqa: RUF001 -- Russian professional qualification questions are intentional.

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.assistant.gateway import ProfessionalAssistantKnowledgeQuery
from asd_kontur.assistant.models import AssistantMode
from asd_kontur.assistant.postgres import AssistantRepository
from asd_kontur.assistant.profiles import (
    CONSTRUCTION_CONSULTANT_MODEL_PROFILE,
    CONSTRUCTION_CONSULTANT_PROFILE,
)
from asd_kontur.assistant.worker import AssistantWorker


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--organization-id", required=True, type=UUID)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--owner-identity", required=True)
    parser.add_argument("--qwen-url", default="http://127.0.0.1:8790/generate")
    parser.add_argument(
        "--matrix",
        type=Path,
        default=Path("tests/fixtures/professional_assistant_quality_matrix_v1.json"),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _mode(case: dict[str, Any]) -> AssistantMode:
    category = str(case["category"])
    if category == "document-conflict":
        return AssistantMode.TENDER
    if category == "missing-data":
        return AssistantMode.RESTORATION
    return AssistantMode.SUPPORT


def _run_turn(
    repository: AssistantRepository,
    worker: AssistantWorker,
    knowledge: ProfessionalAssistantKnowledgeQuery,
    engine: sa.Engine,
    *,
    organization_id: UUID,
    workspace_id: UUID,
    owner_identity: str,
    conversation_id: UUID,
    mode: AssistantMode,
    question: str,
    project_ref: tuple[UUID, int] | None,
) -> dict[str, Any]:
    turn = repository.enqueue_turn(
        organization_id=organization_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        mode=mode,
        question=question,
        owner_identity_id=owner_identity,
        project_ref=project_ref,
        platform_memory_fingerprint=knowledge.memory_fingerprint(),
    )
    started = time.monotonic()
    claimed = repository.claim("construction-consultant-quality-matrix", 900)
    if claimed is None or claimed.turn_id != turn.turn_id:
        raise RuntimeError("quality_matrix_claim_mismatch")
    worker._run(claimed)
    finished = time.monotonic()
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT state,failure_code FROM workspace.assistant_turns WHERE turn_id=:turn"
                ),
                {"turn": turn.turn_id},
            )
            .mappings()
            .one()
        )
        message = (
            connection.execute(
                sa.text(
                    "SELECT content,sources FROM workspace.assistant_messages WHERE turn_id=:turn "
                    "AND role='assistant'"
                ),
                {"turn": turn.turn_id},
            )
            .mappings()
            .one_or_none()
        )
        tools = list(
            connection.execute(
                sa.text(
                    "SELECT tool_name,terminal_outcome FROM workspace.assistant_tool_receipts "
                    "WHERE turn_id=:turn ORDER BY step_sequence"
                ),
                {"turn": turn.turn_id},
            ).mappings()
        )
        quality = (
            connection.execute(
                sa.text(
                    "SELECT answer_type,deterministic_checks,model_checks,passed FROM "
                    "workspace.assistant_quality_receipts WHERE turn_id=:turn"
                ),
                {"turn": turn.turn_id},
            )
            .mappings()
            .one_or_none()
        )
        first_delta = connection.scalar(
            sa.text(
                "SELECT extract(epoch FROM (min(recorded_at)-:created)) FROM "
                "workspace.assistant_turn_events WHERE turn_id=:turn AND event_type='delta'"
            ),
            {"turn": turn.turn_id, "created": turn.created_at},
        )
    return {
        "turn_id": str(turn.turn_id),
        "state": str(row["state"]),
        "failure_code": row["failure_code"],
        "answer": str(message["content"]) if message else "",
        "source_count": len(message["sources"]) if message else 0,
        "tools": [str(item["tool_name"]) for item in tools],
        "tool_outcomes": [str(item["terminal_outcome"]) for item in tools],
        "answer_type": str(quality["answer_type"]) if quality else None,
        "quality_passed": bool(quality and quality["passed"]),
        "deterministic_checks": quality["deterministic_checks"] if quality else {},
        "model_checks": quality["model_checks"] if quality else {},
        "first_text_seconds": round(float(first_delta), 3) if first_delta is not None else None,
        "total_seconds": round(finished - started, 3),
    }


def _rubric(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    answer = result["answer"].casefold()
    required = set(case.get("required_tools", []))
    forbidden = set(case.get("forbidden_tools", []))
    observed = set(result["tools"])
    concepts = [str(item).casefold() for item in case.get("expected_concepts", [])]
    expected_clarification = bool(case.get("clarification"))
    actual_clarification = result["answer_type"] == "clarification"
    old_template_headings = (
        "краткий ответ",
        "практическое пояснение",
        "применимость к текущему окс",
        "что требуется сделать",
        "ограничения или отсутствующие сведения",
    )
    checks = {
        "succeeded": result["state"] == "succeeded" and result["quality_passed"],
        "required_tools": required <= observed,
        "forbidden_tools": not forbidden.intersection(observed),
        "known_facts": all(concept in answer for concept in concepts),
        "clarification": expected_clarification == actual_clarification,
        "not_fixed_template": sum(heading in answer for heading in old_template_headings) < 3,
        "not_quote_list": answer.count("источник:") <= 2,
    }
    return {"passed": all(checks.values()), "checks": checks}


def main() -> None:
    args = _arguments()
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    engine = sa.create_engine(args.database_url)
    repository = AssistantRepository(engine)
    knowledge = ProfessionalAssistantKnowledgeQuery(engine)
    worker = AssistantWorker(
        repository,
        knowledge,
        identity="quality-matrix",
        qwen_url=args.qwen_url,
    )
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT project_definition_id,version FROM workspace.project_definition_versions "
                "WHERE organization_id=:organization AND workspace_id=:workspace "
                "ORDER BY created_at DESC,version DESC LIMIT 1"
            ),
            {"organization": args.organization_id, "workspace": args.workspace_id},
        ).one_or_none()
    project_ref = (row[0], int(row[1])) if row else None
    results: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        conversation = repository.create_conversation(
            organization_id=args.organization_id,
            workspace_id=args.workspace_id,
            owner_identity_id=args.owner_identity,
            title=f"Матрица качества: {case['id']}",
        )
        history_fixture = case.get("history_fixture")
        if history_fixture:
            seed = {
                "three-works-listed": "Какие три вида работ обнаружены на этом объекте?",
                "hydroisolation-selected": "Расскажи о второй, гидроизоляционной работе объекта.",
                "estimate-gap-selected": "Какие расхождения ВОР и сметы обнаружены на объекте?",
            }[str(history_fixture)]
            _run_turn(
                repository,
                worker,
                knowledge,
                engine,
                organization_id=args.organization_id,
                workspace_id=args.workspace_id,
                owner_identity=args.owner_identity,
                conversation_id=conversation.conversation_id,
                mode=_mode(case),
                question=seed,
                project_ref=project_ref,
            )
        result = _run_turn(
            repository,
            worker,
            knowledge,
            engine,
            organization_id=args.organization_id,
            workspace_id=args.workspace_id,
            owner_identity=args.owner_identity,
            conversation_id=conversation.conversation_id,
            mode=_mode(case),
            question=str(case["question"]),
            project_ref=project_ref,
        )
        result.update({"id": case["id"], "category": case["category"]})
        result["rubric"] = _rubric(case, result)
        results.append(result)
        progress = {
            "id": case["id"],
            "passed": result["rubric"]["passed"],
            "seconds": result["total_seconds"],
        }
        print(json.dumps(progress, ensure_ascii=False), flush=True)
    source_counts = [int(item["source_count"]) for item in results]
    receipt = {
        "profile": CONSTRUCTION_CONSULTANT_PROFILE,
        "model_profile": CONSTRUCTION_CONSULTANT_MODEL_PROFILE,
        "matrix_version": matrix["matrix_version"],
        "denominator": len(results),
        "passed": sum(bool(item["rubric"]["passed"]) for item in results),
        "failed": [item["id"] for item in results if not item["rubric"]["passed"]],
        "source_count_distribution": sorted(set(source_counts)),
        "fixed_source_quota": len(set(source_counts)) == 1,
        "mean_first_text_seconds": round(
            sum(float(item["first_text_seconds"] or 0) for item in results) / len(results), 3
        ),
        "mean_total_seconds": round(
            sum(float(item["total_seconds"]) for item in results) / len(results), 3
        ),
        "results": results,
    }
    receipt["receipt_digest"] = semantic_digest(receipt)
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
