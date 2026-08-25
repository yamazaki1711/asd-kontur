"""Argon2 owner authentication and opaque PostgreSQL session service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from asd_kontur.domain import uuid7

from .config import SpineSettings
from .models import SessionPrincipal, SessionTokens, semantic_digest


class AuthErrorCode(StrEnum):
    INVALID_CREDENTIALS = "invalid_credentials"
    RATE_LIMITED = "rate_limited"
    SESSION_INVALID = "session_invalid"
    SESSION_EXPIRED = "session_expired"
    CSRF_INVALID = "csrf_invalid"
    PROFILE_MISMATCH = "session_profile_mismatch"


class AuthError(RuntimeError):
    def __init__(self, code: AuthErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class OwnerAuthService:
    """No raw password/session value crosses this service into persistence."""

    _hasher = PasswordHasher(
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
    )

    def __init__(self, engine: Engine, settings: SpineSettings) -> None:
        self._engine = engine
        self._settings = settings

    def bootstrap_owner(self, *, username: str, password: str, display_name: str) -> str:
        normalized = _normalize_username(username)
        _validate_password(password)
        owner_identity_id = f"owner:{hashlib.sha256(normalized.encode()).hexdigest()[:24]}"
        with Session(self._engine) as session, session.begin():
            existing = session.execute(
                sa.text(
                    "SELECT owner_identity_id,password_hash FROM application.owner_identities "
                    "WHERE normalized_username=:username FOR UPDATE"
                ),
                {"username": normalized},
            ).one_or_none()
            if existing is not None:
                try:
                    valid: bool = self._hasher.verify(existing.password_hash, password)
                except (VerifyMismatchError, InvalidHashError):
                    valid = False
                if not valid:
                    raise AuthError(AuthErrorCode.INVALID_CREDENTIALS)
                return str(existing.owner_identity_id)
            session.execute(
                sa.text(
                    "INSERT INTO application.owner_identities "
                    "(owner_identity_id,normalized_username,display_name,password_hash,status,auth_version) "
                    "VALUES (:identity,:username,:display,:password_hash,'active',1)"
                ),
                {
                    "identity": owner_identity_id,
                    "username": normalized,
                    "display": display_name.strip(),
                    "password_hash": self._hasher.hash(password),
                },
            )
            self._append_audit(
                session,
                owner_identity_id=owner_identity_id,
                event_type="owner.bootstrap",
                outcome="accepted",
                correlation_id=uuid7(),
            )
        return owner_identity_id

    def login(
        self,
        *,
        username: str,
        password: str,
        client_fingerprint: str,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> SessionTokens:
        current = now or datetime.now(UTC)
        normalized = _normalize_username(username)
        username_digest = self._protected_digest(normalized)
        client_digest = self._protected_digest(client_fingerprint)
        error: AuthErrorCode | None = None
        tokens: SessionTokens | None = None
        with Session(self._engine) as session, session.begin():
            failures = int(
                session.scalar(
                    sa.text(
                        "SELECT count(*) FROM application.login_attempts "
                        "WHERE username_digest=:username AND client_fingerprint_digest=:client "
                        "AND outcome IN ('invalid_credentials','rate_limited') "
                        "AND occurred_at >= :window_start"
                    ),
                    {
                        "username": username_digest,
                        "client": client_digest,
                        "window_start": current
                        - timedelta(seconds=self._settings.login_window_seconds),
                    },
                )
                or 0
            )
            if failures >= self._settings.login_max_attempts:
                self._record_attempt(
                    session,
                    username_digest,
                    client_digest,
                    "rate_limited",
                    correlation_id,
                    current,
                )
                error = AuthErrorCode.RATE_LIMITED
            else:
                owner = session.execute(
                    sa.text(
                        "SELECT owner_identity_id,password_hash,status "
                        "FROM application.owner_identities "
                        "WHERE normalized_username=:username"
                    ),
                    {"username": normalized},
                ).one_or_none()
                valid = False
                if owner is not None and owner.status == "active":
                    try:
                        valid = self._hasher.verify(owner.password_hash, password)
                    except (VerifyMismatchError, InvalidHashError):
                        valid = False
                if not valid:
                    self._record_attempt(
                        session,
                        username_digest,
                        client_digest,
                        "invalid_credentials",
                        correlation_id,
                        current,
                    )
                    error = AuthErrorCode.INVALID_CREDENTIALS
                else:
                    assert owner is not None
                    tokens = self._insert_session(
                        session,
                        owner_identity_id=str(owner.owner_identity_id),
                        username=normalized,
                        client_digest=client_digest,
                        correlation_id=correlation_id,
                        now=current,
                        rotation_parent_digest=None,
                    )
                    self._record_attempt(
                        session,
                        username_digest,
                        client_digest,
                        "accepted",
                        correlation_id,
                        current,
                    )
        if error is not None:
            raise AuthError(error)
        assert tokens is not None
        return tokens

    def authenticate(
        self,
        *,
        session_token: str | None,
        client_fingerprint: str,
        now: datetime | None = None,
    ) -> SessionPrincipal:
        if not session_token:
            raise AuthError(AuthErrorCode.SESSION_INVALID)
        current = now or datetime.now(UTC)
        session_digest = _plain_digest(session_token)
        expected_client = self._protected_digest(client_fingerprint)
        with Session(self._engine) as session, session.begin():
            row = session.execute(
                sa.text(
                    "SELECT s.owner_identity_id,o.normalized_username,s.csrf_secret_digest,s.profile,"
                    "s.inactivity_expires_at,s.absolute_expires_at,s.revoked_at,s.client_fingerprint_digest "
                    "FROM application.sessions s JOIN application.owner_identities o "
                    "ON o.owner_identity_id=s.owner_identity_id "
                    "WHERE s.session_id_digest=:digest AND o.status='active' FOR UPDATE OF s"
                ),
                {"digest": session_digest},
            ).one_or_none()
            if row is None or row.revoked_at is not None:
                raise AuthError(AuthErrorCode.SESSION_INVALID)
            if row.profile != self._settings.session_profile.value:
                raise AuthError(AuthErrorCode.PROFILE_MISMATCH)
            if not hmac.compare_digest(str(row.client_fingerprint_digest), expected_client):
                raise AuthError(AuthErrorCode.SESSION_INVALID)
            if current >= row.inactivity_expires_at or current >= row.absolute_expires_at:
                session.execute(
                    sa.text(
                        "UPDATE application.sessions SET revoked_at=:now "
                        "WHERE session_id_digest=:digest AND revoked_at IS NULL"
                    ),
                    {"now": current, "digest": session_digest},
                )
                raise AuthError(AuthErrorCode.SESSION_EXPIRED)
            next_inactivity = min(
                current + timedelta(seconds=self._settings.inactivity_seconds),
                row.absolute_expires_at,
            )
            session.execute(
                sa.text(
                    "UPDATE application.sessions SET last_seen_at=:now,inactivity_expires_at=:expiry "
                    "WHERE session_id_digest=:digest"
                ),
                {"now": current, "expiry": next_inactivity, "digest": session_digest},
            )
            return SessionPrincipal(
                str(row.owner_identity_id),
                str(row.normalized_username),
                session_digest,
                str(row.csrf_secret_digest),
                str(row.profile),
                row.absolute_expires_at,
            )

    def require_csrf(self, principal: SessionPrincipal, csrf_token: str | None) -> None:
        if not csrf_token or not hmac.compare_digest(
            principal.csrf_digest, _plain_digest(csrf_token)
        ):
            raise AuthError(AuthErrorCode.CSRF_INVALID)

    def rotate(
        self,
        *,
        principal: SessionPrincipal,
        client_fingerprint: str,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> SessionTokens:
        current = now or datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            changed = int(
                getattr(
                    session.execute(
                        sa.text(
                            "UPDATE application.sessions SET revoked_at=:now "
                            "WHERE session_id_digest=:digest AND revoked_at IS NULL"
                        ),
                        {"now": current, "digest": principal.session_digest},
                    ),
                    "rowcount",
                    0,
                )
            )
            if changed != 1:
                raise AuthError(AuthErrorCode.SESSION_INVALID)
            return self._insert_session(
                session,
                owner_identity_id=principal.owner_identity_id,
                username=principal.username,
                client_digest=self._protected_digest(client_fingerprint),
                correlation_id=correlation_id,
                now=current,
                rotation_parent_digest=principal.session_digest,
            )

    def logout(
        self, *, principal: SessionPrincipal, correlation_id: UUID, now: datetime | None = None
    ) -> None:
        current = now or datetime.now(UTC)
        with Session(self._engine) as session, session.begin():
            session.execute(
                sa.text(
                    "UPDATE application.sessions SET revoked_at=COALESCE(revoked_at,:now) "
                    "WHERE session_id_digest=:digest"
                ),
                {"now": current, "digest": principal.session_digest},
            )
            self._append_audit(
                session,
                owner_identity_id=principal.owner_identity_id,
                event_type="session.logout",
                outcome="accepted",
                correlation_id=correlation_id,
            )

    def _insert_session(
        self,
        session: Session,
        *,
        owner_identity_id: str,
        username: str,
        client_digest: str,
        correlation_id: UUID,
        now: datetime,
        rotation_parent_digest: str | None,
    ) -> SessionTokens:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        session_digest = _plain_digest(session_token)
        csrf_digest = _plain_digest(csrf_token)
        inactivity_expires = now + timedelta(seconds=self._settings.inactivity_seconds)
        absolute_expires = now + timedelta(seconds=self._settings.absolute_session_seconds)
        session.execute(
            sa.text(
                "INSERT INTO application.sessions "
                "(session_id_digest,owner_identity_id,csrf_secret_digest,profile,issued_at,last_seen_at,"
                "inactivity_expires_at,absolute_expires_at,rotation_parent_digest,client_fingerprint_digest) "
                "VALUES (:session,:owner,:csrf,:profile,:now,:now,:inactivity,:absolute,:parent,:client)"
            ),
            {
                "session": session_digest,
                "owner": owner_identity_id,
                "csrf": csrf_digest,
                "profile": self._settings.session_profile.value,
                "now": now,
                "inactivity": inactivity_expires,
                "absolute": absolute_expires,
                "parent": rotation_parent_digest,
                "client": client_digest,
            },
        )
        event_type = "session.rotated" if rotation_parent_digest else "session.created"
        self._append_audit(
            session,
            owner_identity_id=owner_identity_id,
            event_type=event_type,
            outcome="accepted",
            correlation_id=correlation_id,
        )
        principal = SessionPrincipal(
            owner_identity_id,
            username,
            session_digest,
            csrf_digest,
            self._settings.session_profile.value,
            absolute_expires,
        )
        return SessionTokens(session_token, csrf_token, principal)

    def _protected_digest(self, value: str) -> str:
        return (
            "sha256:"
            + hmac.new(
                self._settings.audit_pepper.encode(), value.encode(), hashlib.sha256
            ).hexdigest()
        )

    @staticmethod
    def _record_attempt(
        session: Session,
        username_digest: str,
        client_digest: str,
        outcome: str,
        correlation_id: UUID,
        occurred_at: datetime,
    ) -> None:
        session.execute(
            sa.text(
                "INSERT INTO application.login_attempts "
                "(login_attempt_id,username_digest,client_fingerprint_digest,outcome,occurred_at,correlation_id) "
                "VALUES (:id,:username,:client,:outcome,:occurred,:correlation)"
            ),
            {
                "id": uuid7(),
                "username": username_digest,
                "client": client_digest,
                "outcome": outcome,
                "occurred": occurred_at,
                "correlation": correlation_id,
            },
        )

    @staticmethod
    def _append_audit(
        session: Session,
        *,
        owner_identity_id: str | None,
        event_type: str,
        outcome: str,
        correlation_id: UUID,
    ) -> None:
        event_id = uuid7()
        session.execute(
            sa.text(
                "INSERT INTO application.auth_audit_events "
                "(auth_audit_event_id,owner_identity_id,event_type,outcome,correlation_id,event_digest) "
                "VALUES (:id,:owner,:event,:outcome,:correlation,:digest)"
            ),
            {
                "id": event_id,
                "owner": owner_identity_id,
                "event": event_type,
                "outcome": outcome,
                "correlation": correlation_id,
                "digest": semantic_digest(
                    {
                        "event_id": event_id,
                        "owner": owner_identity_id,
                        "event": event_type,
                        "outcome": outcome,
                        "correlation": correlation_id,
                    }
                ),
            },
        )


def _plain_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _normalize_username(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not 3 <= len(normalized) <= 128:
        raise AuthError(AuthErrorCode.INVALID_CREDENTIALS)
    return normalized


def _validate_password(value: str) -> None:
    if len(value) < 14 or len(value) > 1024:
        raise ValueError("owner password must be 14..1024 characters")
