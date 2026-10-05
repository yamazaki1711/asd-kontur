"""RLS-scoped persistence for professional assistant conversations and turns."""

# ruff: noqa: E501, RUF001 -- SQL and Russian public messages are intentional.

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.application_spine.models import semantic_digest
from asd_kontur.domain import uuid7

from .models import (
    AssistantMode,
    ClaimedTurn,
    Conversation,
    Message,
    Turn,
    TurnEvent,
    TurnState,
)
from .profiles import CONSTRUCTION_CONSULTANT_MODEL_PROFILE, CONSTRUCTION_CONSULTANT_PROFILE


class AssistantPersistenceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssistantRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine

    def create_conversation(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        owner_identity_id: str,
        title: str,
    ) -> Conversation:
        identity = uuid7()
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            session.execute(
                sa.text(
                    "INSERT INTO workspace.assistant_conversations "
                    "(organization_id,workspace_id,conversation_id,created_by_identity_id,title) "
                    "VALUES (:o,:w,:id,:owner,:title)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "id": identity,
                    "owner": owner_identity_id,
                    "title": title,
                },
            )
        return self.get_conversation(organization_id, workspace_id, identity, owner_identity_id)

    def list_conversations(
        self, organization_id: UUID, workspace_id: UUID, owner_identity_id: str
    ) -> tuple[Conversation, ...]:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT c.conversation_id,c.workspace_id,c.title,c.created_at,"
                    "(SELECT t.mode FROM workspace.assistant_turns t WHERE t.organization_id=c.organization_id "
                    "AND t.workspace_id=c.workspace_id AND t.conversation_id=c.conversation_id "
                    "ORDER BY t.turn_ordinal DESC LIMIT 1) latest_mode,"
                    "(SELECT count(*) FROM workspace.assistant_messages m WHERE "
                    "m.organization_id=c.organization_id AND m.workspace_id=c.workspace_id "
                    "AND m.conversation_id=c.conversation_id) message_count "
                    "FROM workspace.assistant_conversations c WHERE c.organization_id=:o AND "
                    "c.workspace_id=:w AND c.created_by_identity_id=:owner "
                    "ORDER BY c.created_at DESC,c.conversation_id"
                ),
                {"o": organization_id, "w": workspace_id, "owner": owner_identity_id},
            ).mappings()
        return tuple(_conversation(row) for row in rows)

    def get_conversation(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
    ) -> Conversation:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT c.conversation_id,c.workspace_id,c.title,c.created_at,"
                        "(SELECT t.mode FROM workspace.assistant_turns t WHERE t.organization_id=c.organization_id "
                        "AND t.workspace_id=c.workspace_id AND t.conversation_id=c.conversation_id "
                        "ORDER BY t.turn_ordinal DESC LIMIT 1) latest_mode,"
                        "(SELECT count(*) FROM workspace.assistant_messages m WHERE "
                        "m.organization_id=c.organization_id AND m.workspace_id=c.workspace_id "
                        "AND m.conversation_id=c.conversation_id) message_count "
                        "FROM workspace.assistant_conversations c WHERE c.organization_id=:o AND "
                        "c.workspace_id=:w AND c.conversation_id=:id "
                        "AND c.created_by_identity_id=:owner"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "id": conversation_id,
                        "owner": owner_identity_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AssistantPersistenceError("assistant_conversation_not_found")
        return _conversation(row)

    def messages(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        conversation_id: UUID,
        owner_identity_id: str,
    ) -> tuple[Message, ...]:
        self.get_conversation(organization_id, workspace_id, conversation_id, owner_identity_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT * FROM workspace.assistant_messages WHERE organization_id=:o AND "
                    "workspace_id=:w AND conversation_id=:c ORDER BY message_ordinal"
                ),
                {"o": organization_id, "w": workspace_id, "c": conversation_id},
            ).mappings()
        return tuple(_message(row) for row in rows)

    def enqueue_turn(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        conversation_id: UUID,
        mode: AssistantMode,
        question: str,
        owner_identity_id: str,
        project_ref: tuple[UUID, int] | None,
        platform_memory_fingerprint: str,
    ) -> Turn:
        self.get_conversation(organization_id, workspace_id, conversation_id, owner_identity_id)
        normalized = " ".join(question.split())
        if not 2 <= len(normalized) <= 8000:
            raise AssistantPersistenceError("assistant_question_invalid")
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            ordinal = int(
                session.scalar(
                    sa.text(
                        "SELECT coalesce(max(turn_ordinal),0)+1 FROM workspace.assistant_turns WHERE "
                        "organization_id=:o AND workspace_id=:w AND conversation_id=:c"
                    ),
                    {"o": organization_id, "w": workspace_id, "c": conversation_id},
                )
                or 1
            )
            turn_id = uuid7()
            request_digest = semantic_digest(
                {
                    "conversation_id": str(conversation_id),
                    "ordinal": ordinal,
                    "mode": mode.value,
                    "question": normalized,
                    "project_ref": tuple(str(value) for value in project_ref)
                    if project_ref
                    else None,
                    "platform_memory": platform_memory_fingerprint,
                    "profile": CONSTRUCTION_CONSULTANT_PROFILE,
                }
            )
            session.execute(
                sa.text(
                    "INSERT INTO workspace.assistant_turns (organization_id,workspace_id,turn_id,"
                    "conversation_id,turn_ordinal,mode,question,requested_by_identity_id,"
                    "project_definition_id,project_definition_version,platform_memory_fingerprint,"
                    "assistant_profile_version,model_profile_version,state,request_digest) VALUES "
                    "(:o,:w,:turn,:conversation,:ordinal,:mode,:question,:owner,:project,:project_version,"
                    ":memory,:assistant_profile,:model_profile,'queued',:digest)"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "turn": turn_id,
                    "conversation": conversation_id,
                    "ordinal": ordinal,
                    "mode": mode.value,
                    "question": normalized,
                    "owner": owner_identity_id,
                    "project": project_ref[0] if project_ref else None,
                    "project_version": project_ref[1] if project_ref else None,
                    "memory": platform_memory_fingerprint,
                    "assistant_profile": CONSTRUCTION_CONSULTANT_PROFILE,
                    "model_profile": CONSTRUCTION_CONSULTANT_MODEL_PROFILE,
                    "digest": request_digest,
                },
            )
            self._append_event(
                session, organization_id, workspace_id, turn_id, "queued", {"state": "queued"}
            )
            self._insert_message(
                session,
                organization_id,
                workspace_id,
                conversation_id,
                turn_id,
                "user",
                normalized,
                (),
                (),
                None,
                None,
            )
        return self.turn(organization_id, workspace_id, turn_id, owner_identity_id)

    def turn(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        turn_id: UUID,
        owner_identity_id: str,
    ) -> Turn:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT * FROM workspace.assistant_turns WHERE organization_id=:o "
                        "AND workspace_id=:w AND turn_id=:turn "
                        "AND requested_by_identity_id=:owner"
                    ),
                    {
                        "o": organization_id,
                        "w": workspace_id,
                        "turn": turn_id,
                        "owner": owner_identity_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AssistantPersistenceError("assistant_turn_not_found")
        return _turn(row)

    def events(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        turn_id: UUID,
        owner_identity_id: str,
        after: int = 0,
    ) -> tuple[TurnEvent, ...]:
        self.turn(organization_id, workspace_id, turn_id, owner_identity_id)
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            rows = session.execute(
                sa.text(
                    "SELECT event_sequence,event_type,public_payload,recorded_at FROM "
                    "workspace.assistant_turn_events WHERE organization_id=:o AND workspace_id=:w "
                    "AND turn_id=:turn AND event_sequence>:after ORDER BY event_sequence"
                ),
                {"o": organization_id, "w": workspace_id, "turn": turn_id, "after": after},
            ).mappings()
        return tuple(
            TurnEvent(
                int(r["event_sequence"]),
                str(r["event_type"]),
                dict(r["public_payload"]),
                r["recorded_at"],
            )
            for r in rows
        )

    def cancel(
        self,
        organization_id: UUID,
        workspace_id: UUID,
        turn_id: UUID,
        owner_identity_id: str,
    ) -> Turn:
        with Session(self._engine) as session, session.begin():
            _scope(session, organization_id, workspace_id)
            state = session.scalar(
                sa.text(
                    "SELECT state FROM workspace.assistant_turns WHERE "
                    "organization_id=:o AND workspace_id=:w AND turn_id=:turn "
                    "AND requested_by_identity_id=:owner "
                    "FOR UPDATE"
                ),
                {
                    "o": organization_id,
                    "w": workspace_id,
                    "turn": turn_id,
                    "owner": owner_identity_id,
                },
            )
            if state not in {"queued", "leased", "running"}:
                raise AssistantPersistenceError("assistant_turn_not_cancellable")
            if state == "queued":
                session.execute(
                    sa.text(
                        "UPDATE workspace.assistant_turns SET state='cancelled',"
                        "cancellation_requested=true,completed_at=CURRENT_TIMESTAMP WHERE "
                        "organization_id=:o AND workspace_id=:w AND turn_id=:turn"
                    ),
                    {"o": organization_id, "w": workspace_id, "turn": turn_id},
                )
                self._append_event(
                    session,
                    organization_id,
                    workspace_id,
                    turn_id,
                    "cancelled",
                    {
                        "state": "cancelled",
                        "message": "Формирование ответа остановлено.",
                    },
                )
            else:
                session.execute(
                    sa.text(
                        "UPDATE workspace.assistant_turns SET cancellation_requested=true WHERE "
                        "organization_id=:o AND workspace_id=:w AND turn_id=:turn"
                    ),
                    {"o": organization_id, "w": workspace_id, "turn": turn_id},
                )
        return self.turn(organization_id, workspace_id, turn_id, owner_identity_id)

    def claim(self, worker_identity: str, lease_seconds: int) -> ClaimedTurn | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    sa.text("SELECT * FROM workspace.claim_next_assistant_turn(:worker,:lease)"),
                    {"worker": worker_identity, "lease": lease_seconds},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return ClaimedTurn(
            UUID(str(row["organization_id"])),
            UUID(str(row["workspace_id"])),
            UUID(str(row["turn_id"])),
            UUID(str(row["conversation_id"])),
            AssistantMode(str(row["mode"])),
            str(row["question"]),
            str(row["requested_by_identity_id"]),
            int(row["attempt_number"]),
            int(row["lease_generation"]),
        )

    def start(self, claimed: ClaimedTurn) -> None:
        self._state_update(claimed, "running", None)

    def heartbeat(self, claimed: ClaimedTurn, lease_seconds: int) -> bool:
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            row = session.execute(
                sa.text(
                    "UPDATE workspace.assistant_turns SET heartbeat_at=CURRENT_TIMESTAMP,"
                    "lease_expires_at=CURRENT_TIMESTAMP+make_interval(secs=>:lease) WHERE "
                    "organization_id=:o AND workspace_id=:w AND turn_id=:turn AND state='running' "
                    "AND lease_generation=:generation RETURNING cancellation_requested"
                ),
                {
                    "lease": lease_seconds,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "turn": claimed.turn_id,
                    "generation": claimed.lease_generation,
                },
            ).scalar_one()
        return bool(row)

    def append_delta(self, claimed: ClaimedTurn, text: str) -> None:
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            self._append_event(
                session,
                claimed.organization_id,
                claimed.workspace_id,
                claimed.turn_id,
                "delta",
                {"text": text},
            )

    def complete(
        self,
        claimed: ClaimedTurn,
        *,
        content: str,
        context_digest: str,
        sources: tuple[dict[str, Any], ...],
        action_proposals: tuple[dict[str, Any], ...],
        tool_receipts: tuple[dict[str, Any], ...] = (),
        quality_receipt: dict[str, Any] | None = None,
        dialogue_state: dict[str, Any] | None = None,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            response_digest = semantic_digest(
                {"content": content, "sources": sources, "actions": action_proposals}
            )
            session.execute(
                sa.text(
                    "UPDATE workspace.assistant_turns SET state='succeeded',failure_code=NULL,"
                    "context_digest=:context,response_digest=:response,completed_at=CURRENT_TIMESTAMP,"
                    "lease_owner=NULL,lease_expires_at=NULL WHERE organization_id=:o AND workspace_id=:w "
                    "AND turn_id=:turn AND lease_generation=:generation"
                ),
                {
                    "context": context_digest,
                    "response": response_digest,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "turn": claimed.turn_id,
                    "generation": claimed.lease_generation,
                },
            )
            self._insert_message(
                session,
                claimed.organization_id,
                claimed.workspace_id,
                claimed.conversation_id,
                claimed.turn_id,
                "assistant",
                content,
                sources,
                action_proposals,
                "Qwen3.8-27B",
                "qwen3.8-27b-mlx-8bit@1.0.0",
            )
            for receipt in tool_receipts:
                self._insert_tool_receipt(session, claimed, receipt)
            if quality_receipt is not None:
                self._insert_quality_receipt(session, claimed, quality_receipt)
            if dialogue_state is not None:
                self._insert_dialogue_state(session, claimed, dialogue_state)
            for source in sources:
                self._append_event(
                    session,
                    claimed.organization_id,
                    claimed.workspace_id,
                    claimed.turn_id,
                    "source",
                    source,
                )
            self._append_event(
                session,
                claimed.organization_id,
                claimed.workspace_id,
                claimed.turn_id,
                "completed",
                {"state": "succeeded", "response_digest": response_digest},
            )

    def fail(self, claimed: ClaimedTurn, code: str, *, reconciliation: bool = False) -> None:
        if reconciliation:
            target = "reconciliation_required"
        elif code == "assistant_cancelled":
            target = "cancelled"
        else:
            target = "failed"
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            session.execute(
                sa.text(
                    "UPDATE workspace.assistant_turns SET state=:state,failure_code=:code,"
                    "completed_at=CURRENT_TIMESTAMP,lease_owner=NULL,lease_expires_at=NULL WHERE "
                    "organization_id=:o AND workspace_id=:w AND turn_id=:turn AND lease_generation=:generation"
                ),
                {
                    "state": target,
                    "code": code,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "turn": claimed.turn_id,
                    "generation": claimed.lease_generation,
                },
            )
            self._append_event(
                session,
                claimed.organization_id,
                claimed.workspace_id,
                claimed.turn_id,
                target,
                {"state": target, "message": _public_failure(code)},
            )

    def history_for_prompt(
        self, claimed: ClaimedTurn, limit: int = 8
    ) -> tuple[dict[str, str], ...]:
        messages = self.messages(
            claimed.organization_id,
            claimed.workspace_id,
            claimed.conversation_id,
            claimed.requested_by_identity_id,
        )
        return tuple(
            {"role": item.role, "content": item.content[:1200]} for item in messages[-limit:-1]
        )

    def dialogue_state(self, claimed: ClaimedTurn) -> dict[str, Any] | None:
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            row = (
                session.execute(
                    sa.text(
                        "SELECT version,summary,active_subjects,state_fingerprint FROM "
                        "workspace.assistant_dialogue_state_versions WHERE organization_id=:o AND "
                        "workspace_id=:w AND conversation_id=:c ORDER BY version DESC LIMIT 1"
                    ),
                    {
                        "o": claimed.organization_id,
                        "w": claimed.workspace_id,
                        "c": claimed.conversation_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def _state_update(self, claimed: ClaimedTurn, state: str, code: str | None) -> None:
        with Session(self._engine) as session, session.begin():
            _scope(session, claimed.organization_id, claimed.workspace_id)
            result = session.execute(
                sa.text(
                    "UPDATE workspace.assistant_turns SET state=:state,failure_code=:code,"
                    "heartbeat_at=CURRENT_TIMESTAMP WHERE organization_id=:o AND workspace_id=:w "
                    "AND turn_id=:turn AND state='leased' AND lease_generation=:generation"
                ),
                {
                    "state": state,
                    "code": code,
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "turn": claimed.turn_id,
                    "generation": claimed.lease_generation,
                },
            )
            changed = int(getattr(result, "rowcount", 0))
            if changed != 1:
                raise AssistantPersistenceError("assistant_lease_fence_rejected")
            self._append_event(
                session,
                claimed.organization_id,
                claimed.workspace_id,
                claimed.turn_id,
                state,
                {"state": state},
            )

    @staticmethod
    def _append_event(
        session: Session,
        organization_id: UUID,
        workspace_id: UUID,
        turn_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        sequence = int(
            session.scalar(
                sa.text(
                    "SELECT coalesce(max(event_sequence),0)+1 FROM workspace.assistant_turn_events WHERE organization_id=:o AND workspace_id=:w AND turn_id=:turn"
                ),
                {"o": organization_id, "w": workspace_id, "turn": turn_id},
            )
            or 1
        )
        digest = semantic_digest(
            {
                "turn_id": str(turn_id),
                "sequence": sequence,
                "event_type": event_type,
                "payload": payload,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.assistant_turn_events (organization_id,workspace_id,turn_id,event_sequence,event_type,public_payload,event_digest) VALUES (:o,:w,:turn,:sequence,:type,CAST(:payload AS jsonb),:digest)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "turn": turn_id,
                "sequence": sequence,
                "type": event_type,
                "payload": json.dumps(payload, ensure_ascii=False),
                "digest": digest,
            },
        )

    @staticmethod
    def _insert_message(
        session: Session,
        organization_id: UUID,
        workspace_id: UUID,
        conversation_id: UUID,
        turn_id: UUID,
        role: str,
        content: str,
        sources: tuple[dict[str, Any], ...],
        actions: tuple[dict[str, Any], ...],
        model_identity: str | None,
        model_profile: str | None,
    ) -> None:
        ordinal = int(
            session.scalar(
                sa.text(
                    "SELECT coalesce(max(message_ordinal),0)+1 FROM workspace.assistant_messages WHERE organization_id=:o AND workspace_id=:w AND conversation_id=:c"
                ),
                {"o": organization_id, "w": workspace_id, "c": conversation_id},
            )
            or 1
        )
        digest = semantic_digest(
            {
                "conversation_id": str(conversation_id),
                "ordinal": ordinal,
                "role": role,
                "content": content,
                "sources": sources,
                "actions": actions,
            }
        )
        session.execute(
            sa.text(
                "INSERT INTO workspace.assistant_messages (organization_id,workspace_id,message_id,conversation_id,message_ordinal,turn_id,role,content,sources,action_proposals,model_identity,model_profile_version,content_digest) VALUES (:o,:w,:id,:conversation,:ordinal,:turn,:role,:content,CAST(:sources AS jsonb),CAST(:actions AS jsonb),:model,:profile,:digest)"
            ),
            {
                "o": organization_id,
                "w": workspace_id,
                "id": uuid7(),
                "conversation": conversation_id,
                "ordinal": ordinal,
                "turn": turn_id,
                "role": role,
                "content": content,
                "sources": json.dumps(sources, ensure_ascii=False),
                "actions": json.dumps(actions, ensure_ascii=False),
                "model": model_identity,
                "profile": model_profile,
                "digest": digest,
            },
        )

    @staticmethod
    def _insert_tool_receipt(
        session: Session, claimed: ClaimedTurn, receipt: dict[str, Any]
    ) -> None:
        response = receipt.get("response", {})
        response_digest = semantic_digest(response)
        source_ids = tuple(
            str(item.get("source_id"))
            for item in response.get("sources", [])
            if item.get("source_id")
        )
        raw_outcome = str(response.get("outcome", "blocked"))
        if raw_outcome in ("found", "not_found", "blocked"):
            terminal_outcome = raw_outcome
        elif raw_outcome == "document_not_present":
            terminal_outcome = "not_found"
        elif response.get("sources") or response.get("items"):
            terminal_outcome = "found"
        else:
            terminal_outcome = "blocked"
        session.execute(
            sa.text(
                "INSERT INTO workspace.assistant_tool_receipts (organization_id,workspace_id,turn_id,"
                "step_sequence,tool_name,request_payload,planning_reason,terminal_outcome,response_digest,"
                "source_ids) VALUES (:o,:w,:turn,:step,:tool,CAST(:request AS jsonb),:reason,:outcome,"
                ":digest,CAST(:sources AS jsonb))"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "turn": claimed.turn_id,
                "step": int(receipt["step_sequence"]),
                "tool": str(receipt["tool"]),
                "request": json.dumps(receipt["arguments"], ensure_ascii=False),
                "reason": str(receipt["reason"]),
                "outcome": terminal_outcome,
                "digest": response_digest,
                "sources": json.dumps(source_ids, ensure_ascii=False),
            },
        )

    @staticmethod
    def _insert_quality_receipt(
        session: Session, claimed: ClaimedTurn, receipt: dict[str, Any]
    ) -> None:
        fingerprint = semantic_digest(receipt)
        session.execute(
            sa.text(
                "INSERT INTO workspace.assistant_quality_receipts (organization_id,workspace_id,turn_id,"
                "logical_profile,model_profile,planning_profile,synthesis_profile,validation_profile,"
                "intent,answer_type,"
                "deterministic_checks,model_checks,passed,receipt_fingerprint) VALUES "
                "(:o,:w,:turn,:logical,:model_profile,:planning,:synthesis,:validation,:intent,:answer_type,"
                "CAST(:deterministic AS jsonb),CAST(:model AS jsonb),:passed,:fingerprint)"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "turn": claimed.turn_id,
                "logical": str(receipt["logical_profile"]),
                "model_profile": str(receipt["model_profile"]),
                "planning": str(receipt["planning_profile"]),
                "synthesis": str(receipt["synthesis_profile"]),
                "validation": str(receipt["validation_profile"]),
                "intent": str(receipt["intent"]),
                "answer_type": str(receipt["answer_type"]),
                "deterministic": json.dumps(receipt["deterministic_checks"], ensure_ascii=False),
                "model": json.dumps(receipt["model_checks"], ensure_ascii=False),
                "passed": bool(receipt["passed"]),
                "fingerprint": fingerprint,
            },
        )

    @staticmethod
    def _insert_dialogue_state(
        session: Session, claimed: ClaimedTurn, state: dict[str, Any]
    ) -> None:
        version = int(
            session.scalar(
                sa.text(
                    "SELECT coalesce(max(version),0)+1 FROM "
                    "workspace.assistant_dialogue_state_versions WHERE organization_id=:o AND "
                    "workspace_id=:w AND conversation_id=:c"
                ),
                {
                    "o": claimed.organization_id,
                    "w": claimed.workspace_id,
                    "c": claimed.conversation_id,
                },
            )
            or 1
        )
        payload = {
            "conversation_id": str(claimed.conversation_id),
            "version": version,
            "source_turn_id": str(claimed.turn_id),
            "summary": state["summary"],
            "active_subjects": state["active_subjects"],
        }
        session.execute(
            sa.text(
                "INSERT INTO workspace.assistant_dialogue_state_versions (organization_id,workspace_id,"
                "conversation_id,version,source_turn_id,summary,active_subjects,state_fingerprint) VALUES "
                "(:o,:w,:conversation,:version,:turn,:summary,CAST(:subjects AS jsonb),:fingerprint)"
            ),
            {
                "o": claimed.organization_id,
                "w": claimed.workspace_id,
                "conversation": claimed.conversation_id,
                "version": version,
                "turn": claimed.turn_id,
                "summary": str(state["summary"]),
                "subjects": json.dumps(state["active_subjects"], ensure_ascii=False),
                "fingerprint": semantic_digest(payload),
            },
        )


def _scope(session: Session, organization_id: UUID, workspace_id: UUID) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", str(organization_id), True),
            sa.func.set_config("asd.workspace_id", str(workspace_id), True),
        )
    ).one()


def _conversation(row: Any) -> Conversation:
    return Conversation(
        UUID(str(row["conversation_id"])),
        UUID(str(row["workspace_id"])),
        str(row["title"]),
        row["created_at"],
        AssistantMode(str(row["latest_mode"])) if row["latest_mode"] else None,
        int(row["message_count"]),
    )


def _message(row: Any) -> Message:
    return Message(
        UUID(str(row["message_id"])),
        UUID(str(row["conversation_id"])),
        UUID(str(row["turn_id"])),
        int(row["message_ordinal"]),
        str(row["role"]),
        str(row["content"]),
        tuple(dict(x) for x in row["sources"]),
        tuple(dict(x) for x in row["action_proposals"]),
        row["created_at"],
    )


def _turn(row: Any) -> Turn:
    return Turn(
        UUID(str(row["turn_id"])),
        UUID(str(row["conversation_id"])),
        int(row["turn_ordinal"]),
        AssistantMode(str(row["mode"])),
        str(row["question"]),
        TurnState(str(row["state"])),
        str(row["failure_code"]) if row["failure_code"] else None,
        UUID(str(row["project_definition_id"])) if row["project_definition_id"] else None,
        int(row["project_definition_version"]) if row["project_definition_version"] else None,
        row["created_at"],
        row["started_at"],
        row["completed_at"],
    )


def _public_failure(code: str) -> str:
    if code in {
        "qwen_runtime_unavailable",
        "qwen_stream_interrupted",
        "assistant_worker_interrupted",
    }:
        return "Помощник временно недоступен. Повторите вопрос после восстановления сервиса."
    if code == "assistant_cancelled":
        return "Формирование ответа остановлено."
    return "Не удалось сформировать ответ. Повторите вопрос."
