"""Transaction-local scope guards and explicit Unit of Work boundaries."""

from __future__ import annotations

from types import TracebackType

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .repositories import (
    AuditRepository,
    MessagingRepository,
    OrganizationRepository,
    WorkspaceRepository,
)
from .scope import OrganizationContext, WorkspaceContext


class OrganizationUnitOfWork:
    def __init__(self, engine: Engine, context: OrganizationContext) -> None:
        self._engine = engine
        self.context = context
        self.session: Session | None = None
        self.organizations: OrganizationRepository | None = None

    def __enter__(self) -> OrganizationUnitOfWork:
        session = Session(self._engine, autoflush=False, expire_on_commit=False)
        try:
            _set_local_scope(session, str(self.context.organization_id), "")
        except BaseException:
            session.rollback()
            session.close()
            raise
        self.session = session
        self.organizations = OrganizationRepository(session, self.context)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
            self.organizations = None


class WorkspaceUnitOfWork:
    def __init__(self, engine: Engine, context: WorkspaceContext) -> None:
        self._engine = engine
        self.context = context
        self.session: Session | None = None
        self.workspaces: WorkspaceRepository | None = None
        self.audit: AuditRepository | None = None
        self.messaging: MessagingRepository | None = None

    def __enter__(self) -> WorkspaceUnitOfWork:
        session = Session(self._engine, autoflush=False, expire_on_commit=False)
        try:
            _set_local_scope(
                session,
                str(self.context.organization_id),
                str(self.context.workspace_id),
            )
        except BaseException:
            session.rollback()
            session.close()
            raise
        self.session = session
        self.workspaces = WorkspaceRepository(session, self.context)
        self.audit = AuditRepository(session, self.context)
        self.messaging = MessagingRepository(session, self.context)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
            self.workspaces = None
            self.audit = None
            self.messaging = None


def _set_local_scope(session: Session, organization_id: str, workspace_id: str) -> None:
    session.execute(
        sa.select(
            sa.func.set_config("asd.organization_id", organization_id, True),
            sa.func.set_config("asd.workspace_id", workspace_id, True),
        )
    ).one()
