import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactNode, SyntheticEvent, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import { api, requireData } from "./api/client";
import type { components } from "./api/schema";
import { StatusPill } from "./components/StatusPill";
import { PdfEvidenceViewer } from "./viewer/PdfEvidenceViewer";

type Workspace = components["schemas"]["WorkspaceView"];
type Document = components["schemas"]["DocumentView"];
type Job = components["schemas"]["JobView"];
type NtdSeedStatus = components["schemas"]["NtdSeedStatusView"];
type NtdSeedIdentity = components["schemas"]["NtdSeedIdentityView"];
type SupportProduction = components["schemas"]["SupportProductionView"];

const MODES = ["Tender", "Support", "Audit", "Restoration"] as const;

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Authenticated />}>
        <Route element={<ApplicationShell />}>
          <Route index element={<Navigate to="/workspaces" replace />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:workspaceId" element={<WorkspaceHome />} />
          <Route
            path="/workspaces/:workspaceId/documents"
            element={<DocumentsPage />}
          />
          <Route
            path="/workspaces/:workspaceId/documents/:documentId"
            element={<DocumentViewerPage />}
          />
          <Route path="/workspaces/:workspaceId/jobs" element={<JobsPage />} />
          <Route
            path="/workspaces/:workspaceId/evidence"
            element={<EvidenceIndexPage />}
          />
          <Route
            path="/workspaces/:workspaceId/evidence/locators/:locatorId"
            element={<ExactEvidencePage />}
          />
          <Route
            path="/workspaces/:workspaceId/work-matrix"
            element={<WorkMatrixPage />}
          />
          <Route
            path="/workspaces/:workspaceId/project-understanding"
            element={<ProjectUnderstandingPage />}
          />
          <Route
            path="/workspaces/:workspaceId/support-id"
            element={<SupportProductionPage />}
          />
          <Route
            path="/workspaces/:workspaceId/modes/:mode"
            element={<ModePage />}
          />
          <Route path="/platform/knowledge" element={<KnowledgePage />} />
          <Route path="/operations" element={<OperationsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/workspaces" replace />} />
    </Routes>
  );
}

function Authenticated() {
  const session = useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      const { data, error, response } = await api.GET("/api/v1/session");
      if (response.status === 401) return null;
      return requireData(data, error);
    },
    retry: false,
  });
  if (session.isPending)
    return <FullState label="Проверка защищённой сессии…" />;
  if (session.isError || session.data === null)
    return <Navigate to="/login" replace />;
  return <Outlet />;
}

function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/session/login", {
        body: { username, password },
      });
      return requireData(data, error);
    },
    onSuccess: async () => {
      setPassword("");
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      void navigate("/workspaces", { replace: true });
    },
  });
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate();
  };
  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <p className="eyebrow">Локальная доказательная платформа</p>
        <h1 id="login-title">АСД-КОНТУР</h1>
        <p>
          Войдите под bootstrap owner identity. Пароль не сохраняется в
          браузере.
        </p>
        <form onSubmit={submit}>
          <label>
            Пользователь
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {login.isError && <ErrorNotice error={login.error} />}
          <button type="submit" disabled={login.isPending}>
            {login.isPending ? "Вход…" : "Войти"}
          </button>
        </form>
      </section>
    </main>
  );
}

function ApplicationShell() {
  const { workspaceId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/v1/session/logout");
      if (error) throw new Error("logout_failed");
    },
    onSuccess: () => {
      queryClient.clear();
      void navigate("/login", { replace: true });
    },
  });
  const workspaceBase = workspaceId ? `/workspaces/${workspaceId}` : null;
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/workspaces">
          <span className="brand-mark" aria-hidden="true">
            АК
          </span>
          <span>
            <strong>АСД-КОНТУР</strong>
            <small>Product Application Spine</small>
          </span>
        </Link>
        <div className="top-actions">
          <StatusPill tone="warning">ProductApplication PARTIAL</StatusPill>
          <button className="ghost" onClick={() => logout.mutate()}>
            Выйти
          </button>
        </div>
      </header>
      <aside className="sidebar" aria-label="Основная навигация">
        <NavItem to="/workspaces" label="Workspaces" />
        {workspaceBase && (
          <>
            <NavItem to={workspaceBase} label="Current Workspace" end />
            <NavItem to={`${workspaceBase}/documents`} label="Documents" />
            <NavItem to={`${workspaceBase}/jobs`} label="Jobs" />
            <NavItem to={`${workspaceBase}/evidence`} label="Evidence" />
            <NavItem
              to={`${workspaceBase}/project-understanding`}
              label="Project Understanding"
            />
            <NavItem to={`${workspaceBase}/work-matrix`} label="Work Matrix" />
            <NavItem
              to={`${workspaceBase}/support-id`}
              label="Support / ID Package"
            />
            {MODES.map((mode) => (
              <NavItem
                key={mode}
                to={`${workspaceBase}/modes/${mode}`}
                label={mode}
              />
            ))}
          </>
        )}
        <NavItem to="/platform/knowledge" label="Platform Knowledge" />
        <NavItem to="/operations" label="Operations" />
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

function NavItem({
  to,
  label,
  end,
}: {
  to: string;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      {...(end === undefined ? {} : { end })}
      className={({ isActive }) => (isActive ? "active" : "")}
    >
      {label}
    </NavLink>
  );
}

function WorkspacesPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const workspaces = useQuery({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/workspaces");
      return requireData(data, error);
    },
  });
  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/workspaces", {
        body: { display_name: name },
      });
      return requireData(data, error);
    },
    onSuccess: async () => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
  return (
    <Page
      title="Рабочие пространства"
      lead="Изолированные контуры конкретных ОКС. Platform Knowledge не принадлежит ни одному из них."
    >
      <section className="panel compact">
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label>
            Название workspace
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              minLength={3}
              required
            />
          </label>
          <button type="submit" disabled={create.isPending}>
            Создать
          </button>
        </form>
        {create.isError && <ErrorNotice error={create.error} />}
      </section>
      <QueryState query={workspaces} empty="Workspace ещё не созданы.">
        {(items) => (
          <div className="card-grid">
            {items.map((workspace) => (
              <WorkspaceCard
                key={workspace.workspace_id}
                workspace={workspace}
              />
            ))}
          </div>
        )}
      </QueryState>
    </Page>
  );
}

function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  return (
    <article className="entity-card">
      <div className="entity-heading">
        <h2>{workspace.display_name}</h2>
        <StatusPill>{workspace.lifecycle_state}</StatusPill>
      </div>
      <dl>
        <dt>Workspace</dt>
        <dd className="mono">{workspace.workspace_id}</dd>
        <dt>Revision</dt>
        <dd>{workspace.workspace_revision}</dd>
      </dl>
      <Link
        className="button-link"
        to={`/workspaces/${workspace.workspace_id}`}
      >
        Открыть
      </Link>
    </article>
  );
}

function WorkspaceHome() {
  const { workspaceId = "" } = useParams();
  const lifecycle = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/lifecycle",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  return (
    <Page
      title="Контур ОКС"
      lead="Все режимы используют общий ProjectDefinition и WorkRequirementMatrix; раздельные копии доменных данных не создаются."
    >
      <QueryState query={lifecycle}>
        {(workspace) => (
          <>
            <WorkspaceCard workspace={workspace} />
            <WorkspaceResetPanel workspace={workspace} />
          </>
        )}
      </QueryState>
      <div className="card-grid four">
        {MODES.map((mode) => (
          <article className="entity-card" key={mode}>
            <p className="eyebrow">Mode shell</p>
            <h2>{mode}</h2>
            <p>
              Показывает только сохранённые bounded results и явные blockers.
            </p>
            <Link to={`/workspaces/${workspaceId}/modes/${mode}`}>
              Открыть режим
            </Link>
          </article>
        ))}
      </div>
    </Page>
  );
}

function WorkspaceResetPanel({ workspace }: { workspace: Workspace }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [challenge, setChallenge] = useState<
    components["schemas"]["ResetChallengeView"] | null
  >(null);
  const [confirmation, setConfirmation] = useState("");
  const prepare = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/lifecycle/reset/prepare",
        {
          params: { path: { workspace_id: workspace.workspace_id } },
          body: { confirmation: "PREPARE_WORKSPACE_RESET" },
        },
      );
      return requireData(data, error);
    },
    onSuccess: (value) => {
      setChallenge(value);
      setConfirmation("");
    },
  });
  const execute = useMutation({
    mutationFn: async () => {
      if (!challenge) throw new Error("reset_challenge_missing");
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/lifecycle/reset/execute",
        {
          params: { path: { workspace_id: workspace.workspace_id } },
          body: {
            challenge_id: challenge.challenge_id,
            confirmation_text: confirmation,
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      queryClient.removeQueries({
        predicate: (query) => query.queryKey.includes(workspace.workspace_id),
      });
      void navigate("/workspaces", { replace: true });
    },
  });
  return (
    <section className="panel danger-panel" aria-labelledby="reset-title">
      <h2 id="reset-title">Контролируемый reset</h2>
      <p>
        Reset закрывает workspace, создаёт проверяемый локальный архив, очищает
        workspace data и не затрагивает Platform Knowledge. Для local profile
        результат имеет development-assurance, не production attestation.
      </p>
      {!challenge ? (
        <button
          className="danger"
          type="button"
          disabled={prepare.isPending || workspace.lifecycle_state !== "ACTIVE"}
          onClick={() => prepare.mutate()}
        >
          Подготовить reset
        </button>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            execute.mutate();
          }}
        >
          <p className="danger-text">
            Введите точную строку: <code>{challenge.confirmation_text}</code>
          </p>
          <label>
            Подтверждение exact target
            <input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              required
            />
          </label>
          <button
            className="danger"
            type="submit"
            disabled={
              execute.isPending || confirmation !== challenge.confirmation_text
            }
          >
            Выполнить reset
          </button>
        </form>
      )}
      {prepare.isError && <ErrorNotice error={prepare.error} />}
      {execute.isError && <ErrorNotice error={execute.error} />}
    </section>
  );
}

function DocumentsPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState("recorded_desc");
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);
  const documents = useQuery({
    queryKey: ["documents", workspaceId, filter, sort, cursor],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/documents",
        {
          params: {
            path: { workspace_id: workspaceId },
            query: {
              limit: 100,
              cursor,
              processing_status: filter || null,
              sort,
            },
          },
        },
      );
      return requireData(data, error);
    },
  });
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      const form = new FormData();
      const relative: string[] = [];
      for (const file of Array.from(files)) {
        form.append("files", file, file.name);
        relative.push(file.webkitRelativePath || file.name);
      }
      form.append("relative_paths", JSON.stringify(relative));
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/documents",
        {
          params: { path: { workspace_id: workspaceId } },
          body: form as never,
          bodySerializer: (body) => body as unknown as BodyInit,
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] }),
      ]);
    },
  });
  return (
    <Page
      title="Document Registry"
      lead="SourceVersion, digest, processing state и capability gaps без загрузки полного текста в registry response."
    >
      <section className="panel toolbar">
        <label className="upload-button">
          Добавить файлы
          <input
            hidden
            type="file"
            multiple
            onChange={(event) =>
              event.target.files && upload.mutate(event.target.files)
            }
          />
        </label>
        <label className="upload-button secondary">
          Добавить папку
          <input
            hidden
            type="file"
            multiple
            {...({ webkitdirectory: "", directory: "" } as object)}
            onChange={(event) =>
              event.target.files && upload.mutate(event.target.files)
            }
          />
        </label>
        <label>
          Статус
          <select
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              setCursor(null);
              setCursorHistory([]);
            }}
          >
            <option value="">Все</option>
            <option value="complete">complete</option>
            <option value="partial_with_capability_gap">with gap</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label>
          Сортировка
          <select
            value={sort}
            onChange={(event) => {
              setSort(event.target.value);
              setCursor(null);
              setCursorHistory([]);
            }}
          >
            <option value="recorded_desc">Новые сначала</option>
            <option value="recorded_asc">Старые сначала</option>
          </select>
        </label>
      </section>
      {upload.isPending && (
        <InfoNotice>
          Файлы передаются потоково и регистрируются одной manifest-транзакцией…
        </InfoNotice>
      )}
      {upload.isError && <ErrorNotice error={upload.error} />}
      <QueryState query={documents} empty="Document Registry пуст.">
        {(page) => (
          <>
            <DocumentTable documents={page.items} workspaceId={workspaceId} />
            <nav className="pagination" aria-label="Document Registry pages">
              <button
                type="button"
                disabled={cursorHistory.length === 0}
                onClick={() => {
                  const history = [...cursorHistory];
                  setCursor(history.pop() ?? null);
                  setCursorHistory(history);
                }}
              >
                Предыдущая
              </button>
              <button
                type="button"
                disabled={!page.next_cursor}
                onClick={() => {
                  setCursorHistory((value) => [...value, cursor]);
                  setCursor(page.next_cursor);
                }}
              >
                Следующая
              </button>
            </nav>
          </>
        )}
      </QueryState>
    </Page>
  );
}

function DocumentTable({
  documents,
  workspaceId,
}: {
  documents: Document[];
  workspaceId: string;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Документ</th>
            <th>Версия / provenance</th>
            <th>Тип / размер</th>
            <th>Admission</th>
            <th>Extraction</th>
            <th>Pages</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.document_id}>
              <td>
                <Link
                  to={`/workspaces/${workspaceId}/documents/${document.document_id}?page=1`}
                >
                  {document.safe_display_name}
                </Link>
                <small>{document.relative_path}</small>
              </td>
              <td>
                active v{document.version}
                <small>
                  prior: {document.prior_versions.join(", ") || "—"}
                </small>
                <small className="mono">
                  SourceVersion: {document.source_version_id ?? "gap"}
                </small>
                <small>
                  <Link to={`/workspaces/${workspaceId}/jobs`}>
                    jobs: {document.job_ids.length}
                  </Link>
                </small>
              </td>
              <td>
                {document.media_type}
                <small>{formatBytes(document.size_bytes)}</small>
              </td>
              <td>
                <StatusPill>{document.admission_status}</StatusPill>
              </td>
              <td>
                <StatusPill
                  tone={document.capability_gaps.length ? "warning" : "default"}
                >
                  {document.extraction_status}
                </StatusPill>
                {document.capability_gaps.map((gap) => (
                  <small key={gap}>{gap}</small>
                ))}
              </td>
              <td>{document.page_count ?? "—"}</td>
              <td className="mono truncate">{document.content_digest}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentViewerPage() {
  const { workspaceId = "", documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page") || 1));
  return (
    <Page
      title="PDF / Evidence Viewer"
      lead="Viewer визуализирует evidence, но не подтверждает геометрию и не является CAD authority."
    >
      <PdfEvidenceViewer
        workspaceId={workspaceId}
        documentId={documentId}
        page={page}
        onPage={(value) => setParams({ page: String(value) })}
      />
    </Page>
  );
}

function ExactEvidencePage() {
  const { workspaceId = "", locatorId = "" } = useParams();
  const evidence = useQuery({
    queryKey: ["exact-evidence", workspaceId, locatorId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/evidence/locators/{source_locator_id}",
        {
          params: {
            path: {
              workspace_id: workspaceId,
              source_locator_id: locatorId,
            },
          },
        },
      );
      return requireData(data, error);
    },
    retry: false,
  });
  return (
    <Page
      title="Exact Evidence Locator"
      lead="Разрешённая workspace-ссылка на точную страницу/регион и immutable evidence digest."
    >
      <QueryState query={evidence} empty="Evidence locator отсутствует.">
        {(value) => (
          <section className="panel">
            <dl>
              <dt>SourceVersion</dt>
              <dd className="mono">{value.locator.source_version_id}</dd>
              <dt>Locator</dt>
              <dd className="mono">{value.locator.source_locator_id}</dd>
              <dt>Page / region</dt>
              <dd>
                {value.locator.page_number} / {value.locator.region.join(", ")}
              </dd>
              <dt>Evidence digest</dt>
              <dd className="mono truncate">{value.locator.evidence_digest}</dd>
              <dt>Extraction</dt>
              <dd>{value.locator.extraction_method}</dd>
              <dt>Status / authority</dt>
              <dd>
                {value.candidate_fact_status} / {value.authority_type}
              </dd>
            </dl>
            <Link
              to={`/workspaces/${workspaceId}/documents/${value.locator.document_id}?page=${String(value.locator.page_number)}`}
            >
              Открыть документ на странице {value.locator.page_number}
            </Link>
          </section>
        )}
      </QueryState>
    </Page>
  );
}

function JobsPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/jobs",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
    refetchInterval: 5_000,
  });
  useEffect(() => {
    const stream = new EventSource(`/api/v1/workspaces/${workspaceId}/events`);
    stream.onmessage = () =>
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] });
    const refresh = () =>
      void queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] });
    stream.addEventListener("job.succeeded", refresh);
    stream.addEventListener("job.failed", refresh);
    stream.addEventListener("job.reconciliation_required", refresh);
    return () => stream.close();
  }, [queryClient, workspaceId]);
  return (
    <Page
      title="Durable Jobs"
      lead="SSE показывает resumable progress; PostgreSQL остаётся canonical job state."
    >
      <QueryState query={jobs} empty="Jobs отсутствуют.">
        {(items) => <JobTable jobs={items} workspaceId={workspaceId} />}
      </QueryState>
    </Page>
  );
}

function JobTable({ jobs, workspaceId }: { jobs: Job[]; workspaceId: string }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: async (jobId: string) => {
      const { error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/cancel",
        {
          params: { path: { workspace_id: workspaceId, job_id: jobId } },
          body: { confirmation: "CANCEL_JOB" },
        },
      );
      if (error) throw new Error("job_cancellation_failed");
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] }),
  });
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Kind</th>
            <th>State</th>
            <th>Attempts</th>
            <th>Failure</th>
            <th>Terminal receipt</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id}>
              <td>
                {job.job_kind}
                <small className="mono">{job.job_id}</small>
              </td>
              <td>
                <StatusPill
                  tone={
                    job.state === "failed" ||
                    job.state === "reconciliation_required"
                      ? "danger"
                      : "default"
                  }
                >
                  {job.state}
                </StatusPill>
              </td>
              <td>
                {job.attempt_count} / {job.max_attempts}
              </td>
              <td>{job.typed_failure_code ?? "—"}</td>
              <td className="mono truncate">
                {job.terminal_receipt_id ?? "—"}
              </td>
              <td>
                {["queued", "leased", "running"].includes(job.state) && (
                  <button
                    className="ghost"
                    onClick={() => cancel.mutate(job.job_id)}
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceIndexPage() {
  return (
    <Page
      title="Evidence"
      lead="Evidence открывается из точного document/page locator. Выберите документ в Document Registry."
    >
      <InfoNotice>
        Demo evidence запрещён: до выбора зарегистрированного SourceVersion
        панель остаётся пустой.
      </InfoNotice>
    </Page>
  );
}

function WorkMatrixPage() {
  const { workspaceId = "" } = useParams();
  const audit = useMode(workspaceId, "Audit");
  return (
    <Page
      title="WorkRequirementMatrix"
      lead="Одна matrix identity должна использоваться всеми четырьмя режимами."
    >
      <QueryState query={audit}>
        {(view) =>
          view.matrix_version_id ? (
            <pre>{JSON.stringify(view.bounded_results, null, 2)}</pre>
          ) : (
            <GapList gaps={view.gaps} />
          )
        }
      </QueryState>
    </Page>
  );
}

function SupportProductionPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const production = useQuery({
    queryKey: ["support-id-production", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/support/id-production",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  const formPackage = useMutation({
    mutationFn: async (workPackageId: string) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/support/id-packages",
        {
          params: { path: { workspace_id: workspaceId } },
          body: { work_package_id: workPackageId },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["support-id-production", workspaceId],
      });
    },
  });
  const startGeneration = useMutation({
    mutationFn: async (membership: Record<string, unknown>) => {
      const identity = String(membership.membership_id);
      const version = Number(membership.version);
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/support/generation-runs",
        {
          params: { path: { workspace_id: workspaceId } },
          body: {
            membership_id: identity,
            idempotency_key: `support-generation:${identity}:v${String(version)}`,
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["support-id-production", workspaceId],
        }),
        queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] }),
      ]);
    },
  });
  const reviewCandidate = useMutation({
    mutationFn: async (candidateId: string) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/support/generated-candidates/{candidate_id}/review",
        {
          params: {
            path: { workspace_id: workspaceId, candidate_id: candidateId },
          },
          body: { outcome: "approved" },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["support-id-production", workspaceId],
      });
    },
  });
  const finalizeCandidate = useMutation({
    mutationFn: async (candidateId: string) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/support/generated-candidates/{candidate_id}/finalize",
        {
          params: {
            path: { workspace_id: workspaceId, candidate_id: candidateId },
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["support-id-production", workspaceId],
      });
    },
  });
  return (
    <Page
      title="Support / Исполнительная документация"
      lead="От WorkRequirementMatrix к versioned комплекту, реестру, evidence-bound полям и управляемой генерации."
    >
      <QueryState query={production}>
        {(value) => (
          <SupportProductionBody
            value={value}
            workspaceId={workspaceId}
            formPackage={(identity) => formPackage.mutate(identity)}
            packagePending={formPackage.isPending}
            generation={(membership) => startGeneration.mutate(membership)}
            generationPending={startGeneration.isPending}
            review={(identity) => reviewCandidate.mutate(identity)}
            reviewPending={reviewCandidate.isPending}
            finalize={(identity) => finalizeCandidate.mutate(identity)}
            finalizationPending={finalizeCandidate.isPending}
            commandError={
              formPackage.error ??
              startGeneration.error ??
              reviewCandidate.error ??
              finalizeCandidate.error
            }
          />
        )}
      </QueryState>
    </Page>
  );
}

function SupportProductionBody({
  value,
  workspaceId,
  formPackage,
  packagePending,
  generation,
  generationPending,
  review,
  reviewPending,
  finalize,
  finalizationPending,
  commandError,
}: {
  value: SupportProduction;
  workspaceId: string;
  formPackage: (identity: string) => void;
  packagePending: boolean;
  generation: (membership: Record<string, unknown>) => void;
  generationPending: boolean;
  review: (candidateId: string) => void;
  reviewPending: boolean;
  finalize: (candidateId: string) => void;
  finalizationPending: boolean;
  commandError: unknown;
}) {
  const workPackages = Array.from(
    new Set(value.requirements.map((item) => String(item.work_package_id))),
  );
  const readiness = value.readiness as Record<string, unknown> | null;
  const memberships = value.memberships ?? [];
  const registers = value.registers ?? [];
  const fields = value.field_resolutions ?? [];
  return (
    <>
      <section className="panel">
        <div className="entity-heading">
          <h2>Work / ID Requirements</h2>
          <StatusPill tone="warning">
            {value.package ? "package formed" : "package absent"}
          </StatusPill>
        </div>
        {value.requirements.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Документ</th>
                  <th>State</th>
                  <th>Authority</th>
                  <th>Basis / gaps</th>
                </tr>
              </thead>
              <tbody>
                {value.requirements.map((requirement) => (
                  <tr key={String(requirement.document_requirement_id)}>
                    <td>
                      <strong>{String(requirement.document_type)}</strong>
                      <small className="mono">
                        {String(requirement.document_requirement_id)}
                      </small>
                    </td>
                    <td>
                      <StatusPill>
                        {String(requirement.requirement_state)}
                      </StatusPill>
                    </td>
                    <td>{String(requirement.authority_status)}</td>
                    <td>
                      <GapList
                        gaps={[
                          ...((requirement.basis_refs as
                            string[] | undefined) ?? []),
                          ...((requirement.blockers as string[] | undefined) ??
                            []),
                        ]}
                        good={
                          !(
                            (requirement.blockers as unknown[] | undefined)
                              ?.length ?? 0
                          )
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <InfoNotice>
            WorkRequirementMatrix не содержит ID requirements.
          </InfoNotice>
        )}
        {!value.package &&
          workPackages.map((identity) => (
            <button
              key={identity}
              onClick={() => formPackage(identity)}
              disabled={packagePending}
            >
              Сформировать PackageVersion для {identity}
            </button>
          ))}
        {commandError !== null && commandError !== undefined ? (
          <ErrorNotice error={commandError} />
        ) : null}
      </section>

      {value.package && (
        <>
          <section className="metrics" aria-label="Package completeness">
            <Metric
              label="Required"
              value={Number(readiness?.required_count ?? 0)}
            />
            <Metric
              label="Covered"
              value={Number(readiness?.covered_count ?? 0)}
            />
            <Metric
              label="Generated candidate"
              value={Number(readiness?.generated_candidate_count ?? 0)}
            />
            <Metric
              label="Finalized"
              value={Number(readiness?.finalized_count ?? 0)}
            />
            <Metric
              label="Missing"
              value={Number(readiness?.missing_count ?? 0)}
            />
            <Metric
              label="Blocked"
              value={Number(readiness?.blocked_count ?? 0)}
            />
          </section>
          <section className="panel">
            <div className="entity-heading">
              <h2>PackageVersion / ordered memberships</h2>
              <StatusPill tone="warning">
                {displayValue(readiness?.status, "incomplete")}
              </StatusPill>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Role / subject</th>
                    <th>Copies / stage</th>
                    <th>State</th>
                    <th>Action / evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {memberships.map((membership) => {
                    const candidate = membership.generated_candidate_id;
                    const candidateIdentity =
                      typeof candidate === "string" ? candidate : "";
                    const finalizedIdentity =
                      typeof membership.finalized_document_id === "string"
                        ? membership.finalized_document_id
                        : "";
                    const blockers = Array.isArray(membership.blocker_codes)
                      ? membership.blocker_codes.map(String)
                      : [];
                    return (
                      <tr
                        key={`${String(membership.membership_id)}:${String(membership.version)}`}
                      >
                        <td>{String(membership.ordinal)}</td>
                        <td>
                          <strong>{String(membership.role)}</strong>
                          <small className="mono">
                            {String(membership.subject_ref)}
                          </small>
                        </td>
                        <td>
                          {String(membership.required_copy_count)} /{" "}
                          {String(membership.stage)}
                        </td>
                        <td>
                          <StatusPill
                            tone={blockers.length ? "warning" : "default"}
                          >
                            {finalizedIdentity
                              ? "finalized"
                              : candidate
                                ? "generated_candidate"
                                : String(membership.state)}
                          </StatusPill>
                          {Boolean(membership.job_state) && (
                            <small>job: {String(membership.job_state)}</small>
                          )}
                          {Boolean(membership.template_version) && (
                            <small>
                              template {String(membership.template_version)} ·{" "}
                              {displayValue(
                                membership.template_qualification_state,
                                "unqualified",
                              )}
                            </small>
                          )}
                          {Boolean(membership.print_validation_result) && (
                            <small>
                              print:{" "}
                              {String(membership.print_validation_result)}
                            </small>
                          )}
                          {Boolean(membership.review_outcome) && (
                            <small>
                              review: {String(membership.review_outcome)}
                            </small>
                          )}
                        </td>
                        <td>
                          {candidateIdentity ? (
                            <>
                              <a
                                className="button-link"
                                href={`/api/v1/workspaces/${workspaceId}/support/generated-candidates/${candidateIdentity}/content`}
                              >
                                Скачать candidate
                              </a>
                              {!membership.review_outcome && (
                                <button
                                  className="ghost"
                                  onClick={() => review(candidateIdentity)}
                                  disabled={reviewPending}
                                >
                                  Подтвердить review
                                </button>
                              )}
                              {membership.review_outcome === "approved" &&
                                !finalizedIdentity && (
                                  <button
                                    className="ghost"
                                    onClick={() => finalize(candidateIdentity)}
                                    disabled={finalizationPending}
                                  >
                                    Финализировать
                                  </button>
                                )}
                            </>
                          ) : membership.role !== "register" ? (
                            <button
                              className="ghost"
                              onClick={() => generation(membership)}
                              disabled={generationPending}
                            >
                              Запустить generation
                            </button>
                          ) : null}
                          {finalizedIdentity && (
                            <a
                              className="button-link"
                              href={`/api/v1/workspaces/${workspaceId}/support/finalized-documents/${finalizedIdentity}/content`}
                            >
                              Скачать finalized
                            </a>
                          )}
                          <GapList gaps={blockers} good={!blockers.length} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
          <section className="split">
            <article className="panel">
              <h2>Реестр комплекта</h2>
              {registers.map((register) => {
                const manifest = register.register_manifest as Record<
                  string,
                  unknown
                >;
                const documents = Array.isArray(manifest.documents)
                  ? (manifest.documents as Record<string, unknown>[])
                  : [];
                return (
                  <div key={String(register.register_candidate_id)}>
                    <p className="mono">
                      {String(register.manifest_fingerprint)}
                    </p>
                    <ol start={2}>
                      {documents.map((item) => (
                        <li key={String(item.membership_id)}>
                          {String(item.role)} — {String(item.state)}, copies{" "}
                          {String(item.copies)}
                        </li>
                      ))}
                    </ol>
                  </div>
                );
              })}
            </article>
            <article className="panel">
              <h2>Gaps / blockers</h2>
              <GapList gaps={value.gaps} />
            </article>
          </section>
          <section className="panel">
            <h2>Resolved document fields</h2>
            {fields.length ? (
              <dl>
                {fields.map((field) => (
                  <div
                    key={`${String(field.generation_run_id)}:${String(field.field_key)}`}
                  >
                    <dt>{String(field.field_key)}</dt>
                    <dd>
                      {String(field.display_value ?? field.state)}
                      {Boolean(field.source_locator_id) && (
                        <Link
                          to={`/workspaces/${workspaceId}/evidence/locators/${String(field.source_locator_id)}`}
                        >
                          exact evidence
                        </Link>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>GenerationRun ещё не разрешал поля.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}

function ModePage() {
  const { workspaceId = "", mode = "Tender" } = useParams();
  const normalized = MODES.includes(mode as (typeof MODES)[number])
    ? (mode as (typeof MODES)[number])
    : "Tender";
  const view = useMode(workspaceId, normalized);
  return (
    <Page
      title={normalized}
      lead="Mode shell читает общее ядро и не создаёт вымышленные bounded results."
    >
      <QueryState query={view}>
        {(value) => (
          <div className="split">
            <section className="panel">
              <div className="entity-heading">
                <h2>Execution</h2>
                <StatusPill tone="warning">{value.readiness}</StatusPill>
              </div>
              <p>{value.purpose}</p>
              <dl>
                <dt>Execution</dt>
                <dd>{value.execution_state ?? "не запускался"}</dd>
                <dt>Matrix</dt>
                <dd className="mono">{value.matrix_version_id ?? "нет"}</dd>
              </dl>
            </section>
            <section className="panel">
              <h2>Required missing capabilities</h2>
              <GapList gaps={value.missing_capabilities} />
            </section>
          </div>
        )}
      </QueryState>
    </Page>
  );
}

function ProjectUnderstandingPage() {
  const { workspaceId = "" } = useParams();
  const understanding = useQuery({
    queryKey: ["project-understanding", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/project-understanding",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
    retry: false,
  });
  return (
    <Page
      title="Project Understanding"
      lead="Единый evidence-bound ProjectDefinition, состав ОКС, работы и нормативный профиль ПД/РД."
    >
      <QueryState
        query={understanding}
        empty="Обработка документов ещё не сформировала ProjectDefinition."
      >
        {(value) => {
          const definition = value.project_definition.definition as {
            fields?: Record<string, unknown>;
            gaps?: string[];
          };
          const profile = value.normative_profile;
          const profileGaps = (profile?.gaps ?? []) as Array<{
            code?: string;
          }>;
          const evidenceIndex = value.evidence_index as Record<
            string,
            Record<string, unknown>
          >;
          return (
            <>
              <div className="metrics">
                <Metric
                  label="Project fields"
                  value={Object.keys(definition.fields ?? {}).length}
                />
                <Metric
                  label="Page decisions"
                  value={value.page_roles.length}
                />
                <Metric
                  label="Work packages"
                  value={value.work_packages.length}
                />
                <Metric label="Defects" value={value.defects.length} />
              </div>
              <div className="split">
                <section className="panel">
                  <div className="entity-heading">
                    <h2>ProjectDefinition</h2>
                    <StatusPill tone="warning">PARTIAL</StatusPill>
                  </div>
                  <EvidenceObject
                    value={definition.fields ?? {}}
                    workspaceId={workspaceId}
                    evidenceIndex={evidenceIndex}
                  />
                  <h3>Project gaps</h3>
                  <GapList gaps={definition.gaps ?? []} />
                </section>
                <section className="panel">
                  <h2>Applicable PD/RD Normative Profile</h2>
                  {profile ? (
                    <>
                      <dl>
                        <dt>Profile</dt>
                        <dd className="mono">{String(profile.profile_id)}</dd>
                        <dt>Applicable edition date</dt>
                        <dd>
                          {displayValue(
                            profile.applicable_on,
                            "не подтверждена",
                          )}
                        </dd>
                        <dt>Completeness</dt>
                        <dd>{String(profile.completeness_status)}</dd>
                      </dl>
                      <h3>Official corpus denominator</h3>
                      <EvidenceObject
                        value={
                          (profile.corpus_denominator ?? {}) as Record<
                            string,
                            unknown
                          >
                        }
                      />
                      <NormativeRequirementList
                        title="Required PD sections"
                        values={profile.required_pd_sections}
                      />
                      <NormativeRequirementList
                        title="Expected RD sets"
                        values={profile.expected_rd_sets}
                      />
                      <NormativeRequirementList
                        title="Formatting and assembly"
                        values={profile.formatting_requirements}
                      />
                      <h3>Unresolved applicability inputs</h3>
                      <GapList
                        gaps={
                          Array.isArray(profile.unresolved_inputs)
                            ? profile.unresolved_inputs.map(String)
                            : []
                        }
                      />
                      <h3>Normative gaps</h3>
                      <GapList
                        gaps={profileGaps.map(
                          (item) => item.code ?? "NORMATIVE_GAP",
                        )}
                      />
                    </>
                  ) : (
                    <p className="empty-state">
                      Normative profile отсутствует.
                    </p>
                  )}
                </section>
              </div>
              <section className="panel">
                <h2>Work packages</h2>
                {value.work_packages.length ? (
                  <div className="card-grid">
                    {value.work_packages.map((item) => (
                      <WorkPackageCard
                        key={String(item.work_package_id)}
                        item={item}
                        workspaceId={workspaceId}
                        evidenceIndex={evidenceIndex}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="empty-state">
                    WorkPackage candidates отсутствуют.
                  </p>
                )}
              </section>
              <section className="panel">
                <h2>Authority separation</h2>
                <EvidenceObject value={value.authority_layers} />
              </section>
            </>
          );
        }}
      </QueryState>
    </Page>
  );
}

function NormativeRequirementList({
  title,
  values,
}: {
  title: string;
  values: unknown;
}) {
  const rows = Array.isArray(values)
    ? (values as Array<Record<string, unknown>>)
    : [];
  return (
    <section>
      <h3>{title}</h3>
      {rows.length ? (
        <div className="card-grid">
          {rows.map((row) => (
            <article
              className="entity-card"
              key={`${displayValue(row.rule_version_id)}:${displayValue(row.normative_provision_id)}`}
            >
              <strong>
                {displayValue(
                  row.section ?? row.mark ?? row.code,
                  "requirement",
                )}
              </strong>
              <p>Edition: {displayValue(row.normative_edition_id)}</p>
              <p>Provision: {displayValue(row.structural_path)}</p>
              <p>Locator: {displayValue(row.locator)}</p>
              <p className="mono">
                RuleVersion: {displayValue(row.rule_version_id)}
              </p>
              <p className="mono">
                Evidence: {displayValue(row.evidence_digest)}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">no verified result</p>
      )}
    </section>
  );
}

function WorkPackageCard({
  item,
  workspaceId,
  evidenceIndex,
}: {
  item: Record<string, unknown>;
  workspaceId: string;
  evidenceIndex: Record<string, Record<string, unknown>>;
}) {
  const packageValue = (item.package ?? {}) as Record<string, unknown>;
  const workType = (packageValue.work_type ?? {}) as Record<string, unknown>;
  const locators = Array.isArray(packageValue.source_locator_ids)
    ? packageValue.source_locator_ids
    : [];
  return (
    <article className="entity-card">
      <h3>{displayValue(workType.normalized, "unresolved")}</h3>
      <p className="mono">{String(item.work_package_id)}</p>
      <p>
        Evidence:{" "}
        {locators.length
          ? locators.map((locator) => {
              const identity = String(locator);
              const evidence = evidenceIndex[identity];
              return (
                <Link
                  key={identity}
                  to={`/workspaces/${workspaceId}/evidence/locators/${identity}`}
                >
                  {evidence
                    ? `page ${displayValue(evidence.locator_value)}`
                    : identity}
                </Link>
              );
            })
          : "gap"}
      </p>
    </article>
  );
}

function EvidenceObject({
  value,
  workspaceId,
  evidenceIndex,
}: {
  value: Record<string, unknown>;
  workspaceId?: string;
  evidenceIndex?: Record<string, Record<string, unknown>>;
}) {
  return (
    <dl>
      {Object.entries(value).map(([key, raw]) => {
        const item =
          typeof raw === "object" && raw !== null
            ? (raw as Record<string, unknown>)
            : { normalized_value: raw };
        const locatorIdentity = displayValue(item.source_locator_id);
        return (
          <div key={key} className="evidence-field">
            <dt>{key}</dt>
            <dd>
              {displayValue(
                item.normalized_value ?? item.raw_value,
                "no_result",
              )}
            </dd>
            {item.raw_value !== undefined && (
              <dd className="muted">Printed: {displayValue(item.raw_value)}</dd>
            )}
            {item.source_locator_id !== undefined && (
              <dd className="mono">
                {workspaceId ? (
                  <Link
                    to={`/workspaces/${workspaceId}/evidence/locators/${locatorIdentity}`}
                  >
                    Locator: {displayValue(item.source_locator_id)}
                    {evidenceIndex?.[locatorIdentity]
                      ? " (resolved)"
                      : " (gap)"}
                  </Link>
                ) : (
                  <>Locator: {displayValue(item.source_locator_id)}</>
                )}
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}

function displayValue(value: unknown, fallback = "") {
  if (value === undefined || value === null) return fallback;
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

function useMode(workspaceId: string, mode: (typeof MODES)[number]) {
  return useQuery({
    queryKey: ["mode", workspaceId, mode],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/modes/{mode}",
        { params: { path: { workspace_id: workspaceId, mode } } },
      );
      return requireData(data, error);
    },
  });
}

function KnowledgePage() {
  const status = useQuery({
    queryKey: ["knowledge-status"],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/platform/knowledge-status",
      );
      return requireData(data, error);
    },
  });
  const ntdSeed = useQuery({
    queryKey: ["ntd-seed-status"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/platform/ntd-seed-status");
      return requireData(data, error);
    },
  });
  return (
    <Page
      title="Platform Knowledge Status"
      lead="Read-only operational status без выдачи полного canonical knowledge текста."
    >
      <QueryState query={status}>
        {(value) => (
          <>
            <div className="metrics">
              <Metric
                label="Source guidance"
                value={value.source_guidance_count}
              />
              <Metric
                label="Active intelligence"
                value={value.active_intelligence_count}
              />
              <Metric label="Playbooks" value={value.active_playbook_count} />
              <Metric
                label="NTD editions"
                value={value.verified_normative_edition_count}
              />
              <Metric label="RuleVersion" value={value.rule_version_count} />
            </div>
            <section className="panel danger-panel">
              <h2>KnowledgeReady = {String(value.knowledge_ready)}</h2>
              <GapList gaps={value.blockers} />
            </section>
            <section className="panel">
              <h2>Fingerprints</h2>
              <pre>{JSON.stringify(value.semantic_fingerprints, null, 2)}</pre>
            </section>
            <section className="panel">
              <h2>NTD Seed Remediation — exact denominator</h2>
              <QueryState query={ntdSeed}>
                {(seed) => <NtdSeedStatusTable value={seed} />}
              </QueryState>
            </section>
          </>
        )}
      </QueryState>
    </Page>
  );
}

function NtdSeedStatusTable({ value }: { value: NtdSeedStatus }) {
  return (
    <>
      <div className="metrics">
        <Metric label="Denominator" value={value.counts.denominator ?? 0} />
        <Metric
          label="Registered identities"
          value={value.counts.registered_identity_count ?? 0}
        />
        <Metric
          label="Official records"
          value={value.counts.official_record_resolved ?? 0}
        />
        <Metric
          label="Official artifacts"
          value={value.counts.artifact_downloaded ?? 0}
        />
        <Metric
          label="Verified provisions"
          value={value.counts.provisions_verified ?? 0}
        />
        <Metric label="Alignments" value={value.counts.alignments ?? 0} />
        <Metric
          label="Qualified rules"
          value={value.counts.qualified_rules ?? 0}
        />
        <Metric
          label="Rule candidates"
          value={value.counts.rule_candidates ?? 0}
        />
        <Metric label="Active rules" value={value.counts.active_rules ?? 0} />
        <Metric
          label="Qualified / not active"
          value={value.counts.qualified_not_active ?? 0}
        />
      </div>
      <p className="mono">{value.logical_manifest_fingerprint}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Identity / printed edition</th>
              <th>Official resolution</th>
              <th>Artifact</th>
              <th>Pages</th>
              <th>Publication</th>
              <th>Gaps</th>
            </tr>
          </thead>
          <tbody>
            {value.identities.map((identity) => (
              <NtdSeedStatusRow
                key={identity.stable_identity}
                value={identity}
              />
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function NtdSeedStatusRow({ value }: { value: NtdSeedIdentity }) {
  const artifact = value.artifacts[0];
  const preferredResolution =
    value.resolutions.find((item) => item.official_record_url) ??
    value.resolutions[0];
  const gaps = value.resolutions
    .map((item) => item.failure_code)
    .filter((item): item is string => Boolean(item));
  return (
    <tr>
      <td>
        <strong>{value.printed_designations.join("; ")}</strong>
        <small className="mono">{value.stable_identity}</small>
      </td>
      <td>
        <StatusPill
          tone={
            preferredResolution?.official_record_url ? "default" : "warning"
          }
        >
          {preferredResolution?.status ?? "unresolved"}
        </StatusPill>
        <small>{preferredResolution?.provider ?? "—"}</small>
        {preferredResolution?.official_record_url ? (
          <a
            href={preferredResolution.official_record_url}
            target="_blank"
            rel="noreferrer"
          >
            Official record
          </a>
        ) : null}
      </td>
      <td>
        {artifact ? (
          <>
            <StatusPill>downloaded</StatusPill>
            <small>{artifact.edition_label}</small>
            <small className="mono truncate">{artifact.content_digest}</small>
            <a
              href={`/api/v1/platform/ntd/artifacts/${artifact.artifact_id}/content#page=1`}
              target="_blank"
              rel="noreferrer"
            >
              Open admitted source
            </a>
          </>
        ) : (
          <StatusPill tone="warning">metadata-only / blocked</StatusPill>
        )}
      </td>
      <td>
        {artifact ? (
          <>
            {artifact.page_count} total
            <small>{artifact.native_complete_page_count} native complete</small>
            <small>
              {artifact.polza_routed_page_count} external recovery routed
            </small>
            <small>
              {artifact.external_candidate_page_count} candidates received
            </small>
          </>
        ) : (
          "—"
        )}
      </td>
      <td>
        {artifact ? (
          <>
            <small>
              {artifact.verified_provision_count} verified provisions
            </small>
            <small>{artifact.practice_alignment_count} Practice↔NTD</small>
            <small>{artifact.qualified_rule_count} qualified rules</small>
            {artifact.verified_provisions.map((provision) => (
              <details
                key={`${provision.provision_id}:${String(provision.version)}`}
              >
                <summary>
                  {provision.structural_path} · page {provision.page_number}
                </summary>
                <p>{provision.verbatim_text}</p>
                <small>edition: {provision.edition_activation_status}</small>
                <small className="mono truncate">
                  {provision.verification_decision_ref}
                </small>
                {provision.rules.map((rule) => (
                  <div
                    className="evidence-card"
                    key={`${rule.rule_candidate_id}:${String(rule.candidate_version)}`}
                  >
                    <strong>RuleCandidate · {rule.deontic_type}</strong>
                    <StatusPill
                      tone={
                        rule.activation_status === "active"
                          ? "default"
                          : "warning"
                      }
                    >
                      {rule.qualification_status} → {rule.activation_status}
                    </StatusPill>
                    <small>{rule.activation_reason}</small>
                    <small>
                      RuleVersion: {rule.rule_version_id ?? "not compiled"}
                    </small>
                    <small>
                      lifecycle: {rule.rule_lifecycle_status ?? "not started"}
                    </small>
                  </div>
                ))}
                {provision.alignments.map((alignment) => (
                  <div
                    className="evidence-card"
                    key={`${String(alignment.alignment_id)}:${String(alignment.version)}`}
                  >
                    <strong>Practice↔NTD alignment</strong>
                    <StatusPill tone="warning">
                      {String(alignment.status)}
                    </StatusPill>
                    <small className="mono">
                      practice reference:{" "}
                      {String(alignment.practice_guide_reference_id)}
                    </small>
                    <small className="mono">
                      guidance: {String(alignment.guidance_unit_id)}:
                      {String(alignment.guidance_unit_version)}
                    </small>
                    <small>{String(alignment.decision_ref)}</small>
                  </div>
                ))}
                {provision.locators.map((locator, index) => (
                  <a
                    key={String(locator.source_locator_id)}
                    href={`/api/v1/platform/ntd/artifacts/${artifact.artifact_id}/content#page=${String(locator.page)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Evidence {index + 1}: page {String(locator.page)} region{" "}
                    <span className="mono">
                      {JSON.stringify(locator.region)}
                    </span>
                  </a>
                ))}
              </details>
            ))}
          </>
        ) : (
          "—"
        )}
      </td>
      <td>{gaps.length ? <GapList gaps={gaps} /> : <span>—</span>}</td>
    </tr>
  );
}

function OperationsPage() {
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/capabilities");
      return requireData(data, error);
    },
  });
  return (
    <Page
      title="Operations"
      lead="Состояние application slice, recovery и readiness без optimistic PASS."
    >
      <QueryState query={capabilities}>
        {(value) => (
          <div className="split">
            <section className="panel">
              <h2>Implemented</h2>
              <GapList gaps={value.implemented} good />
            </section>
            <section className="panel">
              <h2>Blockers</h2>
              <GapList gaps={value.blockers} />
            </section>
            <section className="panel">
              <h2>Readiness</h2>
              <dl>
                <dt>TrialReady</dt>
                <dd>{String(value.trial_ready)}</dd>
                <dt>OKSReady</dt>
                <dd>{String(value.oks_ready)}</dd>
                <dt>ProductReady</dt>
                <dd>{String(value.product_ready)}</dd>
              </dl>
            </section>
          </div>
        )}
      </QueryState>
    </Page>
  );
}

function Page({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: ReactNode;
}) {
  return (
    <>
      <header className="page-header">
        <p className="eyebrow">ASD-KONTUR / evidence-bound</p>
        <h1>{title}</h1>
        <p>{lead}</p>
      </header>
      {children}
    </>
  );
}
function FullState({ label }: { label: string }) {
  return (
    <main className="center-state" aria-live="polite">
      {label}
    </main>
  );
}
function ErrorNotice({ error }: { error: unknown }) {
  return (
    <div className="notice error" role="alert">
      {error instanceof Error ? error.message : "request_failed"}
    </div>
  );
}
function InfoNotice({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>;
}
function GapList({ gaps, good = false }: { gaps: string[]; good?: boolean }) {
  return gaps.length ? (
    <ul className={good ? "good-list" : "gap-list"}>
      {gaps.map((gap) => (
        <li key={gap}>{gap}</li>
      ))}
    </ul>
  ) : (
    <p>Нет зарегистрированных записей.</p>
  );
}
function Metric({ label, value }: { label: string; value: number }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value.toLocaleString("ru-RU")}</strong>
    </article>
  );
}
function QueryState<T>({
  query,
  children,
  empty = "Нет данных.",
}: {
  query: {
    isPending: boolean;
    isError: boolean;
    error: unknown;
    data: T | undefined;
  };
  children: (value: T) => ReactNode;
  empty?: string;
}) {
  if (query.isPending) return <FullState label="Загрузка…" />;
  if (query.isError || query.data === undefined)
    return <ErrorNotice error={query.error} />;
  if (Array.isArray(query.data) && query.data.length === 0)
    return <InfoNotice>{empty}</InfoNotice>;
  return <>{children(query.data)}</>;
}
function formatBytes(value: number) {
  if (value < 1024) return `${String(value)} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}
