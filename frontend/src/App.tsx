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
            path="/workspaces/:workspaceId/work-matrix"
            element={<WorkMatrixPage />}
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
          <StatusPill tone="warning">MEMORY DATA_DEFECT</StatusPill>
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
            <NavItem to={`${workspaceBase}/work-matrix`} label="Work Matrix" />
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
          </>
        )}
      </QueryState>
    </Page>
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
