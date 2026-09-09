from uuid import UUID, uuid5

from asd_kontur.application_spine.postgres import OWNER_ORGANIZATION_NAMESPACE
from asd_kontur.assistant.construction_consultant_postgres import (
    ConstructionConsultantConversation,
    ConstructionConsultantMessage,
    ConstructionConsultantRepository,
)


class ConstructionConsultantService:
    def __init__(self, repository: ConstructionConsultantRepository) -> None:
        self._repository = repository

    def _organization_id(self, owner_identity_id: str) -> UUID:
        return uuid5(OWNER_ORGANIZATION_NAMESPACE, owner_identity_id)

    def create_conversation(
        self, owner_identity_id: str, title: str | None
    ) -> ConstructionConsultantConversation:
        if title is None:
            normalized_title = "Новый диалог"
        else:
            normalized_title = " ".join(title.split())
            if not (1 <= len(normalized_title) <= 160):
                raise ValueError("construction_consultant_conversation_title_invalid")

        organization_id = self._organization_id(owner_identity_id)
        return self._repository.create_conversation(
            organization_id, owner_identity_id, normalized_title
        )

    def list_conversations(
        self, owner_identity_id: str
    ) -> tuple[ConstructionConsultantConversation, ...]:
        organization_id = self._organization_id(owner_identity_id)
        return self._repository.list_conversations(organization_id, owner_identity_id)

    def messages(
        self, owner_identity_id: str, conversation_id: UUID
    ) -> tuple[ConstructionConsultantMessage, ...]:
        organization_id = self._organization_id(owner_identity_id)
        return self._repository.messages(organization_id, conversation_id, owner_identity_id)
