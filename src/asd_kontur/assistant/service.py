"""Application commands and queries for the professional assistant."""

from __future__ import annotations

from uuid import UUID

from asd_kontur.application_spine.postgres import SpinePostgresRepository

from .gateway import ProfessionalAssistantKnowledgeQuery
from .models import AssistantMode, Conversation, Message, Turn, TurnEvent
from .postgres import AssistantRepository


class ProfessionalAssistantService:
    def __init__(
        self,
        spine: SpinePostgresRepository,
        repository: AssistantRepository,
        knowledge: ProfessionalAssistantKnowledgeQuery,
    ) -> None:
        self._spine = spine
        self._repository = repository
        self._knowledge = knowledge

    def create_conversation(
        self, *, owner_identity_id: str, workspace_id: UUID, title: str | None
    ) -> Conversation:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        normalized = " ".join((title or "Новый диалог").split())
        if not 1 <= len(normalized) <= 160:
            raise ValueError("assistant_conversation_title_invalid")
        return self._repository.create_conversation(
            organization_id=organization_id,
            workspace_id=workspace_id,
            owner_identity_id=owner_identity_id,
            title=normalized,
        )

    def list_conversations(
        self, *, owner_identity_id: str, workspace_id: UUID
    ) -> tuple[Conversation, ...]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.list_conversations(organization_id, workspace_id, owner_identity_id)

    def messages(
        self, *, owner_identity_id: str, workspace_id: UUID, conversation_id: UUID
    ) -> tuple[Message, ...]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.messages(
            organization_id, workspace_id, conversation_id, owner_identity_id
        )

    def ask(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        conversation_id: UUID,
        mode: AssistantMode,
        question: str,
    ) -> Turn:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        project = self._spine.project_understanding_view(
            owner_identity_id=owner_identity_id, workspace_id=workspace_id
        )
        project_row = dict((project or {}).get("project_definition") or {})
        project_ref = (
            (UUID(str(project_row["project_definition_id"])), int(project_row["version"]))
            if project_row.get("project_definition_id") and project_row.get("version")
            else None
        )
        return self._repository.enqueue_turn(
            organization_id=organization_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            mode=mode,
            question=question,
            owner_identity_id=owner_identity_id,
            project_ref=project_ref,
            platform_memory_fingerprint=self._knowledge.memory_fingerprint(),
        )

    def turn(self, *, owner_identity_id: str, workspace_id: UUID, turn_id: UUID) -> Turn:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.turn(organization_id, workspace_id, turn_id, owner_identity_id)

    def events(
        self,
        *,
        owner_identity_id: str,
        workspace_id: UUID,
        turn_id: UUID,
        after: int = 0,
    ) -> tuple[TurnEvent, ...]:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.events(
            organization_id, workspace_id, turn_id, owner_identity_id, after
        )

    def cancel(self, *, owner_identity_id: str, workspace_id: UUID, turn_id: UUID) -> Turn:
        organization_id = self._spine.resolve_scope(owner_identity_id, workspace_id)
        return self._repository.cancel(organization_id, workspace_id, turn_id, owner_identity_id)
