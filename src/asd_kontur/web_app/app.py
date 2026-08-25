"""FastAPI transport adapter with authentication, CSRF and static SPA serving."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import Engine

from asd_kontur.domain import uuid7
from asd_kontur.lifecycle import LifecycleError, PostgresLifecycleRepository

from ..application_spine.auth import AuthError, OwnerAuthService
from ..application_spine.config import SpineSettings
from ..application_spine.models import ModeName, SessionPrincipal
from ..application_spine.object_store import WorkspaceObjectStore
from ..application_spine.postgres import SpinePersistenceError, SpinePostgresRepository
from ..application_spine.reset import WorkspaceResetService
from ..application_spine.services import ProductSpineService, UploadPart
from .schemas import (
    CapabilityStatusView,
    DocumentPage,
    ErrorDetail,
    ErrorEnvelope,
    EvidencePanelView,
    HealthView,
    JobCancellationRequest,
    JobView,
    KnowledgeStatusView,
    LoginRequest,
    ModeView,
    ResetChallengeView,
    ResetExecuteRequest,
    ResetPrepareRequest,
    ResetReceiptView,
    SessionView,
    UploadBatchView,
    WorkspaceCreate,
    WorkspaceView,
)

API_PREFIX = "/api/v1"
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")


class ApplicationContainer:
    def __init__(self, engine: Engine, settings: SpineSettings) -> None:
        self.engine = engine
        self.lifecycle_engine = sa.create_engine(
            settings.lifecycle_database_url, pool_pre_ping=True
        )
        self.destruction_engine = sa.create_engine(
            settings.destruction_database_url, pool_pre_ping=True
        )
        self.settings = settings
        self.repository = SpinePostgresRepository(
            engine,
            event_retention_seconds=settings.event_retention_seconds,
        )
        self.object_store = WorkspaceObjectStore(
            settings.object_store_root,
            chunk_bytes=settings.upload_chunk_bytes,
            max_file_bytes=settings.max_file_bytes,
        )
        self.auth = OwnerAuthService(engine, settings)
        self.service = ProductSpineService(
            self.repository,
            PostgresLifecycleRepository(self.lifecycle_engine),
            self.object_store,
            settings,
        )
        self.reset_service = WorkspaceResetService(
            repository=self.repository,
            lifecycle=PostgresLifecycleRepository(self.lifecycle_engine),
            lifecycle_engine=self.lifecycle_engine,
            destruction_engine=self.destruction_engine,
            object_store=self.object_store,
            archive_store_root=settings.archive_store_root,
        )


def create_app(*, engine: Engine, settings: SpineSettings) -> FastAPI:
    container = ApplicationContainer(engine, settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()
        container.lifecycle_engine.dispose()
        container.destruction_engine.dispose()

    app = FastAPI(
        title="ASD-KONTUR Product Application Spine API",
        version="1.0.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=(
            f"{API_PREFIX}/docs"
            if settings.session_profile.value == "development_loopback"
            else None
        ),
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = container
    _install_middleware(app)
    app.include_router(_api_router())
    _install_static_routes(app, settings.frontend_dist)
    return app


def _install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_and_correlation(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = uuid7()
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
            "worker-src 'self' blob:; connect-src 'self'; object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
        status_code = 429 if exc.code.value == "rate_limited" else 401
        return _error(request, exc.code.value, status_code)

    @app.exception_handler(SpinePersistenceError)
    async def persistence_error(request: Request, exc: SpinePersistenceError) -> JSONResponse:
        status_code = 404 if exc.code.endswith("not_found") else 409
        return _error(request, exc.code, status_code)

    @app.exception_handler(LifecycleError)
    async def lifecycle_error(request: Request, exc: LifecycleError) -> JSONResponse:
        return _error(request, exc.code.value, 409)

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return _error(request, str(exc), 422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error(request, "request_validation_failed", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = str(exc.detail) if isinstance(exc.detail, str) else "http_request_rejected"
        return _error(request, code, exc.status_code)


def _api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health/live", response_model=HealthView, tags=["health"])
    def live() -> HealthView:
        return HealthView(status="live")

    @router.get("/health/ready", response_model=HealthView, tags=["health"])
    def ready(request: Request) -> HealthView:
        try:
            head = _container(request).repository.migration_head()
            checks = {"postgresql": "reachable", "migration_head": head}
            expected = "0018_product_spine"
            return HealthView(
                status="ready" if head == expected else "not_ready",
                checks=checks,
            )
        except (sa.exc.SQLAlchemyError, SpinePersistenceError):
            return HealthView(status="not_ready", checks={"postgresql": "unavailable"})

    @router.post("/session/login", response_model=SessionView, tags=["session"])
    def login(request: Request, payload: LoginRequest, response: Response) -> SessionView:
        container = _container(request)
        tokens = container.auth.login(
            username=payload.username,
            password=payload.password,
            client_fingerprint=_client_fingerprint(request),
            correlation_id=request.state.correlation_id,
        )
        _set_session_cookies(response, container.settings, tokens.session_token, tokens.csrf_token)
        return _session_view(tokens.principal)

    @router.get("/session", response_model=SessionView, tags=["session"])
    def session_info(principal: Annotated[SessionPrincipal, Depends(_principal)]) -> SessionView:
        return _session_view(principal)

    @router.post("/session/rotate", response_model=SessionView, tags=["session"])
    def rotate(
        request: Request,
        response: Response,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> SessionView:
        container = _container(request)
        tokens = container.auth.rotate(
            principal=principal,
            client_fingerprint=_client_fingerprint(request),
            correlation_id=request.state.correlation_id,
        )
        _set_session_cookies(response, container.settings, tokens.session_token, tokens.csrf_token)
        return _session_view(tokens.principal)

    @router.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["session"])
    def logout(
        request: Request,
        response: Response,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> None:
        container = _container(request)
        container.auth.logout(
            principal=principal,
            correlation_id=request.state.correlation_id,
        )
        response.delete_cookie(container.settings.session_cookie_name, path="/")
        response.delete_cookie(container.settings.csrf_cookie_name, path="/")

    @router.get("/capabilities", response_model=CapabilityStatusView, tags=["platform"])
    def capabilities(_: Annotated[SessionPrincipal, Depends(_principal)]) -> CapabilityStatusView:
        return CapabilityStatusView(**ProductSpineService.capability_status())

    @router.get("/workspaces", response_model=list[WorkspaceView], tags=["workspaces"])
    def list_workspaces(
        request: Request,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> list[WorkspaceView]:
        values = _container(request).service.list_workspaces(
            owner_identity_id=principal.owner_identity_id
        )
        return [WorkspaceView(**jsonable_encoder(asdict(value))) for value in values]

    @router.post("/workspaces", response_model=WorkspaceView, status_code=201, tags=["workspaces"])
    def create_workspace(
        request: Request,
        payload: WorkspaceCreate,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> WorkspaceView:
        value = _container(request).service.create_workspace(
            owner_identity_id=principal.owner_identity_id,
            display_name=payload.display_name,
            correlation_id=request.state.correlation_id,
        )
        return WorkspaceView(**jsonable_encoder(asdict(value)))

    @router.get(
        "/workspaces/{workspace_id}/lifecycle",
        response_model=WorkspaceView,
        tags=["workspaces"],
    )
    def lifecycle(
        request: Request,
        workspace_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> WorkspaceView:
        value = _container(request).repository.get_workspace(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
        )
        return WorkspaceView(**jsonable_encoder(asdict(value)))

    @router.post(
        "/workspaces/{workspace_id}/lifecycle/reset/prepare",
        response_model=ResetChallengeView,
        tags=["workspaces"],
    )
    def prepare_workspace_reset(
        request: Request,
        workspace_id: UUID,
        payload: ResetPrepareRequest,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> ResetChallengeView:
        del payload
        value = _container(request).reset_service.prepare(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            correlation_id=request.state.correlation_id,
        )
        return ResetChallengeView(**jsonable_encoder(asdict(value)))

    @router.post(
        "/workspaces/{workspace_id}/lifecycle/reset/execute",
        response_model=ResetReceiptView,
        tags=["workspaces"],
    )
    def execute_workspace_reset(
        request: Request,
        workspace_id: UUID,
        payload: ResetExecuteRequest,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> ResetReceiptView:
        value = _container(request).reset_service.execute(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            challenge_id=payload.challenge_id,
            confirmation_text=payload.confirmation_text,
            correlation_id=request.state.correlation_id,
        )
        return ResetReceiptView(**jsonable_encoder(asdict(value)))

    @router.post(
        "/workspaces/{workspace_id}/documents",
        response_model=UploadBatchView,
        status_code=202,
        tags=["documents"],
    )
    def upload_documents(
        request: Request,
        workspace_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
        files: Annotated[list[UploadFile], File()],
        relative_paths: Annotated[str | None, Form()] = None,
    ) -> UploadBatchView:
        relative = json.loads(relative_paths) if relative_paths else []
        if not isinstance(relative, list) or any(not isinstance(item, str) for item in relative):
            raise ValueError("relative_paths_manifest_invalid")
        if relative and len(relative) != len(files):
            raise ValueError("relative_paths_manifest_mismatch")
        parts = tuple(
            UploadPart(
                index,
                file.filename or f"upload-{index}",
                relative[index - 1] if relative else None,
                file.content_type,
                None,
                None,
                file.file,
            )
            for index, file in enumerate(files, start=1)
        )
        value = _container(request).service.register_uploads(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            parts=parts,
            correlation_id=request.state.correlation_id,
        )
        return UploadBatchView(**jsonable_encoder(asdict(value)))

    @router.get(
        "/workspaces/{workspace_id}/documents",
        response_model=DocumentPage,
        tags=["documents"],
    )
    def list_documents(
        request: Request,
        workspace_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
        limit: int = 50,
        cursor: str | None = None,
        media_type: str | None = None,
        processing_status: str | None = None,
        sort: str = "recorded_desc",
    ) -> DocumentPage:
        if limit < 1 or limit > 200:
            raise ValueError("pagination_limit_invalid")
        values, next_cursor = _container(request).service.list_documents(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
            media_type=media_type,
            status=processing_status,
            sort=sort,
        )
        return DocumentPage(
            items=[jsonable_encoder(asdict(value)) for value in values],
            next_cursor=next_cursor,
        )

    @router.get("/workspaces/{workspace_id}/documents/{document_id}/content", tags=["documents"])
    def document_content(
        request: Request,
        workspace_id: UUID,
        document_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
        range_header: Annotated[str | None, Header(alias="Range")] = None,
    ) -> StreamingResponse:
        provisional = _container(request).repository.get_document(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            document_id=document_id,
        )
        requested = _parse_range(range_header, provisional.size_bytes)
        value = _container(request).service.document_content(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            document_id=document_id,
            byte_range=requested,
        )
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(value.length),
            "ETag": f'"{value.content_digest[7:]}"',
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{_header_filename(value.safe_display_name)}"
            ),
        }
        response_status = 200
        if requested is not None:
            headers["Content-Range"] = (
                f"bytes {value.offset}-{value.offset + value.length - 1}/{value.size_bytes}"
            )
            response_status = 206
        return StreamingResponse(
            value.chunks,
            media_type=value.media_type,
            status_code=response_status,
            headers=headers,
        )

    @router.get("/workspaces/{workspace_id}/jobs", response_model=list[JobView], tags=["jobs"])
    def jobs(
        request: Request,
        workspace_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> list[JobView]:
        return [
            JobView(**jsonable_encoder(asdict(value)))
            for value in _container(request).service.list_jobs(
                owner_identity_id=principal.owner_identity_id,
                workspace_id=workspace_id,
            )
        ]

    @router.post(
        "/workspaces/{workspace_id}/jobs/{job_id}/cancel",
        status_code=202,
        tags=["jobs"],
    )
    def cancel_job(
        request: Request,
        workspace_id: UUID,
        job_id: UUID,
        payload: JobCancellationRequest,
        principal: Annotated[SessionPrincipal, Depends(_mutation_principal)],
    ) -> dict[str, str]:
        del payload
        _container(request).service.cancel_job(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            job_id=job_id,
        )
        return {"status": "cancellation_requested"}

    @router.get("/workspaces/{workspace_id}/events", tags=["jobs"])
    async def events(
        request: Request,
        workspace_id: UUID,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        after = int(last_event_id or 0)
        service = _container(request).service
        service.progress_events(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            after_sequence=after,
        )

        async def stream() -> AsyncIterator[str]:
            cursor = after
            idle_ticks = 0
            while not await request.is_disconnected():
                values = service.progress_events(
                    owner_identity_id=principal.owner_identity_id,
                    workspace_id=workspace_id,
                    after_sequence=cursor,
                )
                if values:
                    idle_ticks = 0
                    for value in values:
                        cursor = value.sequence
                        payload = json.dumps(jsonable_encoder(asdict(value)), separators=(",", ":"))
                        yield f"id: {cursor}\nevent: {value.event_type}\ndata: {payload}\n\n"
                else:
                    idle_ticks += 1
                    if idle_ticks >= 10:
                        yield ": heartbeat\n\n"
                        idle_ticks = 0
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get(
        "/workspaces/{workspace_id}/evidence/{document_id}/pages/{page_number}",
        response_model=EvidencePanelView,
        tags=["evidence"],
    )
    def evidence(
        request: Request,
        workspace_id: UUID,
        document_id: UUID,
        page_number: int,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> EvidencePanelView:
        value = _container(request).service.evidence(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            document_id=document_id,
            page_number=page_number,
        )
        return EvidencePanelView(**jsonable_encoder(asdict(value)))

    @router.get("/workspaces/{workspace_id}/modes/{mode}", response_model=ModeView, tags=["modes"])
    def mode_view(
        request: Request,
        workspace_id: UUID,
        mode: ModeName,
        principal: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> ModeView:
        value = _container(request).service.mode_view(
            owner_identity_id=principal.owner_identity_id,
            workspace_id=workspace_id,
            mode=mode,
        )
        return ModeView(**jsonable_encoder(asdict(value)))

    @router.get("/platform/knowledge-status", response_model=KnowledgeStatusView, tags=["platform"])
    def knowledge_status(
        request: Request,
        _: Annotated[SessionPrincipal, Depends(_principal)],
    ) -> KnowledgeStatusView:
        value = _container(request).service.knowledge_status()
        return KnowledgeStatusView(**jsonable_encoder(asdict(value)))

    return router


def _container(request: Request) -> ApplicationContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def _principal(request: Request) -> SessionPrincipal:
    container = _container(request)
    return container.auth.authenticate(
        session_token=request.cookies.get(container.settings.session_cookie_name),
        client_fingerprint=_client_fingerprint(request),
    )


def _mutation_principal(
    request: Request,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> SessionPrincipal:
    principal = _principal(request)
    _container(request).auth.require_csrf(principal, x_csrf_token)
    return principal


def _client_fingerprint(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    agent = request.headers.get("user-agent", "unknown")[:512]
    return f"{host}|{agent}"


def _session_view(principal: SessionPrincipal) -> SessionView:
    return SessionView(
        owner_identity_id=principal.owner_identity_id,
        username=principal.username,
        profile=principal.profile,
        absolute_expires_at=principal.absolute_expires_at,
    )


def _set_session_cookies(
    response: Response,
    settings: SpineSettings,
    session_token: str,
    csrf_token: str,
) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="strict",
        path="/",
        max_age=settings.absolute_session_seconds,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.secure_cookie,
        samesite="strict",
        path="/",
        max_age=settings.absolute_session_seconds,
    )


def _parse_range(value: str | None, size: int) -> tuple[int, int] | None:
    if value is None:
        return None
    match = RANGE_PATTERN.fullmatch(value.strip())
    if match is None or "," in value:
        raise HTTPException(status_code=416, detail="document_range_not_satisfiable")
    start_text, end_text = match.groups()
    if not start_text:
        length = int(end_text or 0)
        if length < 1:
            raise HTTPException(status_code=416, detail="document_range_not_satisfiable")
        return max(size - length, 0), size - 1
    start = int(start_text)
    end = min(int(end_text), size - 1) if end_text else size - 1
    if start >= size or end < start:
        raise HTTPException(status_code=416, detail="document_range_not_satisfiable")
    return start, end


def _header_filename(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _error(request: Request, code: str, status_code: int) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=code.replace("_", " "),
            correlation_id=request.state.correlation_id,
        )
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(envelope))


def _install_static_routes(app: FastAPI, frontend_dist: Path | None) -> None:
    if frontend_dist is None:
        return
    root = frontend_dist.resolve(strict=True)
    assets = root / "assets"
    if not (root / "index.html").is_file() or not assets.is_dir():
        raise ValueError("frontend production bundle is incomplete")

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    def asset(asset_path: str) -> FileResponse:
        target = (assets / asset_path).resolve(strict=True)
        if assets not in target.parents or not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type=mimetypes.guess_type(target)[0])

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa(spa_path: str) -> FileResponse:
        if spa_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (root / spa_path).resolve(strict=False)
        if candidate.is_file() and (candidate == root or root in candidate.parents):
            return FileResponse(candidate)
        return FileResponse(root / "index.html", media_type="text/html")
