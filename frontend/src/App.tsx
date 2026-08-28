import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactNode, SyntheticEvent, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
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
type ModeName = (typeof MODES)[number];

const MODE_DEFINITIONS: Record<
  ModeName,
  {
    slug: string;
    title: string;
    purpose: string;
    results: string;
    nextAction: string;
  }
> = {
  Tender: {
    slug: "tender",
    title: "Тендерный анализ",
    purpose:
      "Проверка договора, ПД/РД, ведомостей объёмов работ, смет и требований заказчика.",
    results:
      "Риски, неучтённые работы и материалы, замечания к исходным данным, протокол разногласий и предложения по договору.",
    nextAction: "Загрузить и проверить исходные документы",
  },
  Support: {
    slug: "support",
    title: "Инженерное сопровождение",
    purpose:
      "Сопровождение СМР, контроль исходных данных, работ, материалов и корректное формирование исполнительной документации.",
    results:
      "Структура работ, требования к контролю, комплект ИД, реестр, акты и другие поддержанные документы.",
    nextAction: "Открыть комплект исполнительной документации",
  },
  Audit: {
    slug: "audit",
    title: "Аудит",
    purpose:
      "Проверка проектной, рабочей и исполнительной документации, фактических данных и состояния комплектности.",
    results: "Несоответствия, пробелы, риски, замечания и план устранения.",
    nextAction: "Проверить состав загруженных документов",
  },
  Restoration: {
    slug: "restoration",
    title: "Восстановление",
    purpose:
      "Восстановление состояния исполнительной документации по имеющимся документам, журналам, актам, схемам и подтверждённым фактам.",
    results:
      "Перечень недостающего, восстановленные проекты документов и комплект ИД без фабрикации отсутствующих фактов.",
    nextAction: "Оценить доступные исходные данные",
  },
};

function modeFromSlug(value?: string): ModeName | null {
  return (
    MODES.find(
      (mode) => MODE_DEFINITIONS[mode].slug === value?.toLowerCase(),
    ) ?? null
  );
}

function workspaceRoute(mode: ModeName, workspaceId: string, suffix = "") {
  return `/modes/${MODE_DEFINITIONS[mode].slug}/workspaces/${workspaceId}${suffix}`;
}

function workspaceRouteFromSlug(
  modeSlug: string | undefined,
  workspaceId: string,
  suffix = "",
) {
  const mode = modeFromSlug(modeSlug);
  return mode
    ? workspaceRoute(mode, workspaceId, suffix)
    : `/workspaces/${workspaceId}${suffix}`;
}

function displayWorkspaceName(value: string) {
  return /synthetic/i.test(value) ? "Демонстрационный объект" : value;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Authenticated />}>
        <Route element={<ApplicationShell />}>
          <Route index element={<Navigate to="/modes" replace />} />
          <Route path="/modes" element={<ModeSelectionPage />} />
          <Route path="/modes/:mode/workspaces" element={<WorkspacesPage />} />
          <Route
            path="/modes/:mode/workspaces/:workspaceId"
            element={<ModePage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/documents"
            element={<DocumentsPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/documents/:documentId"
            element={<DocumentViewerPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/jobs"
            element={<JobsPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/evidence"
            element={<EvidenceIndexPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/evidence/locators/:locatorId"
            element={<ExactEvidencePage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/work-matrix"
            element={<WorkMatrixPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/project-understanding"
            element={<ProjectUnderstandingPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/support-id"
            element={<SupportProductionPage />}
          />
          <Route path="/admin/knowledge" element={<KnowledgePage />} />
          <Route path="/admin/system" element={<OperationsPage />} />
          <Route
            path="/admin/workspaces/:workspaceId/reset"
            element={<AdminWorkspaceResetPage />}
          />
          <Route
            path="/workspaces"
            element={<Navigate to="/modes" replace />}
          />
          <Route
            path="/workspaces/:workspaceId/*"
            element={<LegacyModeGate />}
          />
          <Route
            path="/platform/knowledge"
            element={<Navigate to="/admin/knowledge" replace />}
          />
          <Route
            path="/operations"
            element={<Navigate to="/admin/system" replace />}
          />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/modes" replace />} />
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
      void navigate("/modes", { replace: true });
    },
  });
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    login.mutate();
  };
  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <h1 id="login-title">АСД-КОНТУР</h1>
        <p className="login-subtitle">Вход в комплекс</p>
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
  const { workspaceId, mode: modeSlug } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mode = modeFromSlug(modeSlug);
  const isAdmin = location.pathname.startsWith("/admin/");
  const isSelection = !workspaceId && !isAdmin;
  const session = useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/session");
      return requireData(data, error);
    },
  });
  const workspace = useQuery({
    queryKey: ["workspace", workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/lifecycle",
        { params: { path: { workspace_id: workspaceId ?? "" } } },
      );
      return requireData(data, error);
    },
  });
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
  const workspaceBase =
    workspaceId && mode ? workspaceRoute(mode, workspaceId) : null;
  return (
    <div
      className={`app-shell${isSelection || isAdmin ? " app-shell-simple" : ""}`}
    >
      <header className="topbar">
        <Link className="brand" to="/modes">
          <span className="brand-mark" aria-hidden="true">
            АК
          </span>
          <span>
            <strong>АСД-КОНТУР</strong>
            {workspace.data && mode && (
              <small>
                {displayWorkspaceName(workspace.data.display_name)} ·{" "}
                {MODE_DEFINITIONS[mode].title}
              </small>
            )}
          </span>
        </Link>
        <div className="top-actions">
          {workspaceBase && mode && (
            <>
              <Link
                className="top-link"
                to={`/modes/${MODE_DEFINITIONS[mode].slug}/workspaces`}
              >
                Сменить объект
              </Link>
              <Link className="top-link" to="/modes">
                Сменить режим
              </Link>
            </>
          )}
          {isAdmin && (
            <Link className="top-link" to="/modes">
              К выбору режима
            </Link>
          )}
          <span className="profile-name">{session.data?.username}</span>
          <button className="ghost" onClick={() => logout.mutate()}>
            Выйти
          </button>
        </div>
      </header>
      {workspaceBase && mode && (
        <aside className="sidebar" aria-label="Разделы объекта">
          <NavItem to={workspaceBase} label="Обзор" end />
          <NavItem to={`${workspaceBase}/documents`} label="Документы" />
          <NavItem to={`${workspaceBase}/jobs`} label="Обработка" />
          <NavItem
            to={`${workspaceBase}/project-understanding`}
            label="Исходные данные"
          />
          <NavItem
            to={`${workspaceBase}/work-matrix`}
            label="Работы и требования"
          />
          {mode === "Support" && (
            <NavItem
              to={`${workspaceBase}/support-id`}
              label="Исполнительная документация"
            />
          )}
          <NavItem
            to={`${workspaceBase}/evidence`}
            label="Исходные подтверждения"
          />
        </aside>
      )}
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
  const { mode: modeSlug } = useParams();
  const mode = modeFromSlug(modeSlug);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [recentWorkspaceByMode, setRecentWorkspaceByMode] = useState<
    Partial<Record<ModeName, string>>
  >({});
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
    onSuccess: async (workspace) => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      if (mode) {
        window.localStorage.setItem(
          `asd-recent-${MODE_DEFINITIONS[mode].slug}`,
          workspace.workspace_id,
        );
        void navigate(workspaceRoute(mode, workspace.workspace_id));
      }
    },
  });
  if (!mode) return <Navigate to="/modes" replace />;
  const recentWorkspaceId =
    recentWorkspaceByMode[mode] ??
    window.localStorage.getItem(`asd-recent-${MODE_DEFINITIONS[mode].slug}`);
  return (
    <Page
      title="Выберите объект"
      lead={`Режим «${MODE_DEFINITIONS[mode].title}». Откройте существующий ОКС или создайте новый.`}
    >
      <section className="panel compact">
        <h2>Создать объект</h2>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label>
            Название объекта
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              minLength={3}
              required
            />
          </label>
          <button type="submit" disabled={create.isPending}>
            Создать объект
          </button>
        </form>
        {create.isError && <ErrorNotice error={create.error} />}
      </section>
      <div className="section-heading">
        <h2>Доступные объекты</h2>
        <Link to="/modes">Сменить режим</Link>
      </div>
      <QueryState query={workspaces} empty="Доступных объектов пока нет.">
        {(items) => {
          const activeItems = items.filter(
            (workspace) => workspace.lifecycle_state === "ACTIVE",
          );
          const recent = activeItems.find(
            (workspace) => workspace.workspace_id === recentWorkspaceId,
          );
          const remember = (identity: string) => {
            window.localStorage.setItem(
              `asd-recent-${MODE_DEFINITIONS[mode].slug}`,
              identity,
            );
            setRecentWorkspaceByMode((current) => ({
              ...current,
              [mode]: identity,
            }));
          };
          return (
            <>
              {!activeItems.length && (
                <InfoNotice>Доступных объектов пока нет.</InfoNotice>
              )}
              {recent && (
                <section
                  className="recent-object"
                  aria-labelledby="recent-title"
                >
                  <h2 id="recent-title">Последний открытый</h2>
                  <WorkspaceCard
                    workspace={recent}
                    mode={mode}
                    onOpen={remember}
                  />
                </section>
              )}
              <div className="card-grid">
                {activeItems
                  .filter(
                    (workspace) => workspace.workspace_id !== recentWorkspaceId,
                  )
                  .map((workspace) => (
                    <WorkspaceCard
                      key={workspace.workspace_id}
                      workspace={workspace}
                      mode={mode}
                      onOpen={remember}
                    />
                  ))}
              </div>
            </>
          );
        }}
      </QueryState>
    </Page>
  );
}

function WorkspaceCard({
  workspace,
  mode,
  onOpen,
}: {
  workspace: Workspace;
  mode: ModeName;
  onOpen?: (identity: string) => void;
}) {
  return (
    <article className="entity-card">
      <div className="entity-heading">
        <h2>{displayWorkspaceName(workspace.display_name)}</h2>
        <StatusPill>
          {workspace.lifecycle_state === "ACTIVE"
            ? "В работе"
            : "Недоступен для изменений"}
        </StatusPill>
      </div>
      <p>Объект доступен для работы в выбранном режиме.</p>
      <Link
        className="button-link"
        to={workspaceRoute(mode, workspace.workspace_id)}
        onClick={() => onOpen?.(workspace.workspace_id)}
      >
        Открыть
      </Link>
    </article>
  );
}

function ModeSelectionPage() {
  return (
    <Page
      title="Выберите режим работы"
      lead="Выберите задачу, которую необходимо выполнить. Один объект можно открывать в разных режимах."
    >
      <div className="mode-grid">
        {MODES.map((mode) => (
          <article className="mode-card" key={mode}>
            <span className="mode-number">0{MODES.indexOf(mode) + 1}</span>
            <h2>{MODE_DEFINITIONS[mode].title}</h2>
            <p>{MODE_DEFINITIONS[mode].purpose}</p>
            <h3>Результаты работы</h3>
            <p>{MODE_DEFINITIONS[mode].results}</p>
            <Link
              className="card-action"
              to={`/modes/${MODE_DEFINITIONS[mode].slug}/workspaces`}
            >
              Выбрать режим
            </Link>
          </article>
        ))}
      </div>
    </Page>
  );
}

function LegacyModeGate() {
  const { workspaceId = "" } = useParams();
  const location = useLocation();
  const marker = `/workspaces/${workspaceId}`;
  const suffix = location.pathname.startsWith(marker)
    ? location.pathname.slice(marker.length)
    : "";
  return (
    <Page
      title="Выберите режим работы"
      lead="Ссылка ведёт к объекту без указания текущей задачи. Выберите режим — система не будет определять его за вас."
    >
      <div className="mode-grid compact-modes">
        {MODES.map((mode) => (
          <article className="mode-card" key={mode}>
            <h2>{MODE_DEFINITIONS[mode].title}</h2>
            <p>{MODE_DEFINITIONS[mode].purpose}</p>
            <Link
              className="card-action"
              to={workspaceRoute(mode, workspaceId, suffix)}
            >
              Продолжить
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

function AdminWorkspaceResetPage() {
  const { workspaceId = "" } = useParams();
  const workspace = useQuery({
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
      title="Сброс данных объекта"
      lead="Административная операция полного удаления рабочего состояния выбранного объекта."
    >
      <QueryState query={workspace}>
        {(value) => <WorkspaceResetPanel workspace={value} />}
      </QueryState>
    </Page>
  );
}

function DocumentsPage() {
  const { workspaceId = "", mode } = useParams();
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
      title="Документы объекта"
      lead="Загруженные исходные документы, их версии и состояние обработки."
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
            <option value="complete">Обработан</option>
            <option value="partial_with_capability_gap">
              Требует дополнения
            </option>
            <option value="failed">Ошибка обработки</option>
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
      <QueryState query={documents} empty="Документы ещё не загружены.">
        {(page) => (
          <>
            <DocumentTable
              documents={page.items}
              workspaceId={workspaceId}
              modeSlug={mode}
            />
            <nav className="pagination" aria-label="Страницы списка документов">
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
  modeSlug,
}: {
  documents: Document[];
  workspaceId: string;
  modeSlug?: string | undefined;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Документ</th>
            <th>Версия и источник</th>
            <th>Тип / размер</th>
            <th>Приём</th>
            <th>Обработка</th>
            <th>Страниц</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.document_id}>
              <td>
                <Link
                  to={`${workspaceRouteFromSlug(modeSlug, workspaceId, `/documents/${document.document_id}`)}?page=1`}
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
                  <Link
                    to={workspaceRouteFromSlug(modeSlug, workspaceId, "/jobs")}
                  >
                    заданий обработки: {document.job_ids.length}
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
      title="Просмотр документа"
      lead="Исходный документ с переходом к точной странице и отмеченной области."
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
  const { workspaceId = "", locatorId = "", mode } = useParams();
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
      title="Точное место в исходном документе"
      lead="Страница и область исходного документа, на которых основано выбранное сведение."
    >
      <QueryState
        query={evidence}
        empty="Связь с исходным документом отсутствует."
      >
        {(value) => (
          <section className="panel">
            <dl>
              <dt>Версия источника</dt>
              <dd className="mono">{value.locator.source_version_id}</dd>
              <dt>Идентификатор места</dt>
              <dd className="mono">{value.locator.source_locator_id}</dd>
              <dt>Страница и область</dt>
              <dd>
                {value.locator.page_number} / {value.locator.region.join(", ")}
              </dd>
              <dt>Контрольная сумма фрагмента</dt>
              <dd className="mono truncate">{value.locator.evidence_digest}</dd>
              <dt>Способ извлечения</dt>
              <dd>{value.locator.extraction_method}</dd>
              <dt>Состояние и тип источника</dt>
              <dd>
                {value.candidate_fact_status} / {value.authority_type}
              </dd>
            </dl>
            <Link
              to={`${workspaceRouteFromSlug(mode, workspaceId, `/documents/${value.locator.document_id}`)}?page=${String(value.locator.page_number)}`}
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
      title="Обработка документов"
      lead="Текущие и завершённые задания обработки загруженных материалов."
    >
      <QueryState query={jobs} empty="Заданий обработки пока нет.">
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
            <th>Вид обработки</th>
            <th>Состояние</th>
            <th>Попытки</th>
            <th>Причина ошибки</th>
            <th>Результат</th>
            <th>Действие</th>
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
                  {humanizeStatus(job.state)}
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
                    Отменить
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
      title="Исходные подтверждения"
      lead="Откройте документ, чтобы перейти к странице и области, из которых получено выбранное сведение."
    >
      <InfoNotice>
        Выберите зарегистрированный документ. Система не показывает условные
        сведения без связи с исходным материалом.
      </InfoNotice>
    </Page>
  );
}

function WorkMatrixPage() {
  const { workspaceId = "" } = useParams();
  const audit = useMode(workspaceId, "Audit");
  return (
    <Page
      title="Работы и требования"
      lead="Структура работ объекта и связанные требования к контролю и документам."
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
  const { workspaceId = "", mode } = useParams();
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
      title="Исполнительная документация"
      lead="Требования к документам, состав комплекта, реестр и подготовка поддержанных форм."
    >
      <QueryState query={production}>
        {(value) => (
          <SupportProductionBody
            value={value}
            workspaceId={workspaceId}
            modeSlug={mode}
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
  modeSlug,
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
  modeSlug?: string | undefined;
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
  const packageHistory = value.package_history ?? [];
  const registerHistory = value.register_history ?? [];
  const fields = value.field_resolutions ?? [];
  return (
    <>
      <section className="panel">
        <div className="entity-heading">
          <h2>Требования к исполнительной документации</h2>
          <StatusPill tone="warning">
            {value.package ? "Комплект сформирован" : "Комплект не сформирован"}
          </StatusPill>
        </div>
        {value.requirements.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Документ</th>
                  <th>Состояние</th>
                  <th>Основание</th>
                  <th>Требования и пробелы</th>
                </tr>
              </thead>
              <tbody>
                {value.requirements.map((requirement) => (
                  <tr key={String(requirement.document_requirement_id)}>
                    <td>
                      <strong>
                        {humanizeDocumentRole(
                          String(requirement.document_type),
                        )}
                      </strong>
                    </td>
                    <td>
                      <StatusPill>
                        {humanizeStatus(String(requirement.requirement_state))}
                      </StatusPill>
                    </td>
                    <td>
                      {humanizeStatus(String(requirement.authority_status))}
                    </td>
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
            Для выбранной работы требования к исполнительной документации ещё не
            определены.
          </InfoNotice>
        )}
        {!value.package &&
          workPackages.map((identity) => (
            <button
              key={identity}
              onClick={() => formPackage(identity)}
              disabled={packagePending}
            >
              Сформировать комплект
            </button>
          ))}
        {commandError !== null && commandError !== undefined ? (
          <ErrorNotice error={commandError} />
        ) : null}
      </section>

      {value.package && (
        <>
          <section className="metrics" aria-label="Комплектность пакета">
            <Metric
              label="Требуется"
              value={Number(readiness?.required_count ?? 0)}
            />
            <Metric
              label="Учтено"
              value={Number(readiness?.covered_count ?? 0)}
            />
            <Metric
              label="Подготовлено"
              value={Number(readiness?.generated_candidate_count ?? 0)}
            />
            <Metric
              label="Финализировано"
              value={Number(readiness?.finalized_count ?? 0)}
            />
            <Metric
              label="Отсутствует"
              value={Number(readiness?.missing_count ?? 0)}
            />
            <Metric
              label="Заблокировано"
              value={Number(readiness?.blocked_count ?? 0)}
            />
          </section>
          <section className="panel">
            <div className="entity-heading">
              <h2>Состав комплекта</h2>
              <StatusPill tone="warning">
                {displayValue(readiness?.status, "incomplete")}
              </StatusPill>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Документ</th>
                    <th>Экземпляры и этап</th>
                    <th>Состояние</th>
                    <th>Действие и основание</th>
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
                          <strong>
                            {humanizeDocumentRole(String(membership.role))}
                          </strong>
                        </td>
                        <td>
                          {String(membership.required_copy_count)} /{" "}
                          {String(membership.stage)}
                        </td>
                        <td>
                          <StatusPill
                            tone={blockers.length ? "warning" : "default"}
                          >
                            {humanizeStatus(
                              finalizedIdentity
                                ? "finalized"
                                : candidate
                                  ? "generated_candidate"
                                  : String(membership.state),
                            )}
                          </StatusPill>
                          {Boolean(membership.job_state) && (
                            <small>
                              обработка:{" "}
                              {humanizeStatus(String(membership.job_state))}
                            </small>
                          )}
                          {Boolean(membership.template_version) && (
                            <small>
                              форма {String(membership.template_version)} ·{" "}
                              {humanizeStatus(
                                displayValue(
                                  membership.template_qualification_state,
                                  "unqualified",
                                ),
                              )}
                            </small>
                          )}
                          {Boolean(membership.print_validation_result) && (
                            <small>
                              печатная форма:{" "}
                              {humanizeStatus(
                                String(membership.print_validation_result),
                              )}
                            </small>
                          )}
                          {Boolean(membership.review_outcome) && (
                            <small>
                              проверка:{" "}
                              {humanizeStatus(
                                String(membership.review_outcome),
                              )}
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
                                Скачать проект документа
                              </a>
                              {!membership.review_outcome && (
                                <button
                                  className="ghost"
                                  onClick={() => review(candidateIdentity)}
                                  disabled={reviewPending}
                                >
                                  Подтвердить проверку
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
                              Подготовить документ
                            </button>
                          ) : null}
                          {finalizedIdentity && (
                            <a
                              className="button-link"
                              href={`/api/v1/workspaces/${workspaceId}/support/finalized-documents/${finalizedIdentity}/content`}
                            >
                              Скачать финализированный документ
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
          <section className="panel">
            <h2>История версий комплекта и реестра</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Версия комплекта</th>
                    <th>Состав</th>
                    <th>Версия реестра</th>
                    <th>Контрольная сумма</th>
                  </tr>
                </thead>
                <tbody>
                  {packageHistory.map((packageVersion) => {
                    const version = Number(packageVersion.version);
                    const registerVersion = registerHistory.find(
                      (item) => Number(item.id_package_version) === version,
                    );
                    const manifest = (registerVersion?.register_manifest ??
                      {}) as Record<string, unknown>;
                    const documents = Array.isArray(manifest.documents)
                      ? manifest.documents
                      : [];
                    return (
                      <tr key={String(packageVersion.version)}>
                        <td>Версия комплекта {String(version)}</td>
                        <td>{String(documents.length)} документов</td>
                        <td>
                          {registerVersion
                            ? `Версия реестра ${String(version)}`
                            : "Не сформирована"}
                        </td>
                        <td className="mono">
                          {displayValue(
                            registerVersion?.manifest_fingerprint,
                            "REGISTER_VERSION_MISSING",
                          )}
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
                          {humanizeDocumentRole(String(item.role))} —{" "}
                          {humanizeStatus(String(item.state))}, экземпляров{" "}
                          {String(item.copies)}
                        </li>
                      ))}
                    </ol>
                  </div>
                );
              })}
            </article>
            <article className="panel">
              <h2>Что мешает завершению</h2>
              <GapList gaps={value.gaps.map(humanizeGap)} />
            </article>
          </section>
          <section className="panel">
            <h2>Заполненные поля документа</h2>
            {fields.length ? (
              <dl>
                {fields.map((field) => (
                  <div
                    key={`${String(field.generation_run_id)}:${String(field.field_key)}`}
                  >
                    <dt>{humanizeFieldKey(String(field.field_key))}</dt>
                    <dd>
                      {String(field.display_value ?? field.state)}
                      {Boolean(field.source_locator_id) && (
                        <Link
                          to={workspaceRouteFromSlug(
                            modeSlug,
                            workspaceId,
                            `/evidence/locators/${String(field.source_locator_id)}`,
                          )}
                        >
                          открыть источник
                        </Link>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>Поля документа ещё не подготовлены.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}

function ModePage() {
  const { workspaceId = "", mode } = useParams();
  const normalized = modeFromSlug(mode);
  const view = useMode(workspaceId, normalized ?? "Tender");
  if (!normalized) return <Navigate to="/modes" replace />;
  const definition = MODE_DEFINITIONS[normalized];
  return (
    <Page title={definition.title} lead={definition.purpose}>
      <QueryState query={view}>
        {(value) => (
          <div className="mode-home">
            <section className="panel mode-summary">
              <div className="entity-heading">
                <h2>Текущее состояние</h2>
                <StatusPill tone="warning">
                  {humanizeReadiness(value.readiness)}
                </StatusPill>
              </div>
              <div className="mode-facts">
                <div>
                  <strong>{value.available_inputs.length}</strong>
                  <span>источников данных доступно</span>
                </div>
                <div>
                  <strong>{Object.keys(value.bounded_results).length}</strong>
                  <span>результатов подготовлено</span>
                </div>
                <div>
                  <strong>
                    {value.gaps.length + value.missing_capabilities.length}
                  </strong>
                  <span>вопросов требуют решения</span>
                </div>
              </div>
            </section>
            <section className="panel">
              <h2>Профессиональные результаты</h2>
              <p>{definition.results}</p>
              {normalized === "Support" ? (
                <Link
                  className="button-link"
                  to={workspaceRoute(normalized, workspaceId, "/support-id")}
                >
                  {definition.nextAction}
                </Link>
              ) : (
                <Link
                  className="button-link"
                  to={workspaceRoute(normalized, workspaceId, "/documents")}
                >
                  {definition.nextAction}
                </Link>
              )}
            </section>
            <section className="panel">
              <h2>Что уже доступно</h2>
              {value.available_inputs.length ? (
                <p>
                  Загруженные документы и сведения объекта готовы для работы в
                  этом режиме.
                </p>
              ) : (
                <p>Исходные документы ещё не загружены.</p>
              )}
            </section>
            <section className="panel">
              <h2>Что требуется сделать</h2>
              {value.gaps.length || value.missing_capabilities.length ? (
                <p>
                  Для полного профессионального результата нужны дополнительные
                  исходные данные или поддержка следующих этапов обработки.
                </p>
              ) : (
                <p>Зарегистрированных препятствий нет.</p>
              )}
            </section>
          </div>
        )}
      </QueryState>
    </Page>
  );
}

function ProjectUnderstandingPage() {
  const { workspaceId = "", mode } = useParams();
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
      title="Исходные данные объекта"
      lead="Состав объекта, проектные сведения, работы и применимые нормативные требования."
    >
      <QueryState
        query={understanding}
        empty="Обработка документов ещё не сформировала описание объекта."
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
                  label="Сведений об объекте"
                  value={Object.keys(definition.fields ?? {}).length}
                />
                <Metric
                  label="Разобрано страниц"
                  value={value.page_roles.length}
                />
                <Metric
                  label="Пакетов работ"
                  value={value.work_packages.length}
                />
                <Metric label="Замечаний" value={value.defects.length} />
              </div>
              <div className="split">
                <section className="panel">
                  <div className="entity-heading">
                    <h2>Описание объекта</h2>
                    <StatusPill tone="warning">
                      Сформировано частично
                    </StatusPill>
                  </div>
                  <EvidenceObject
                    value={definition.fields ?? {}}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                    evidenceIndex={evidenceIndex}
                  />
                  <h3>Недостающие сведения</h3>
                  <GapList gaps={(definition.gaps ?? []).map(humanizeGap)} />
                </section>
                <section className="panel">
                  <h2>Применимые нормативные требования</h2>
                  {profile ? (
                    <>
                      <dl>
                        <dt>Версия профиля</dt>
                        <dd className="mono">{String(profile.profile_id)}</dd>
                        <dt>Дата применимости</dt>
                        <dd>
                          {displayValue(
                            profile.applicable_on,
                            "не подтверждена",
                          )}
                        </dd>
                        <dt>Комплектность</dt>
                        <dd>
                          {humanizeStatus(String(profile.completeness_status))}
                        </dd>
                      </dl>
                      <h3>Состав нормативных источников</h3>
                      <EvidenceObject
                        value={
                          (profile.corpus_denominator ?? {}) as Record<
                            string,
                            unknown
                          >
                        }
                      />
                      <NormativeRequirementList
                        title="Требуемые разделы ПД"
                        values={profile.required_pd_sections}
                      />
                      <NormativeRequirementList
                        title="Ожидаемые комплекты РД"
                        values={profile.expected_rd_sets}
                      />
                      <NormativeRequirementList
                        title="Оформление и сборка"
                        values={profile.formatting_requirements}
                      />
                      <h3>Неуточнённые условия применимости</h3>
                      <GapList
                        gaps={
                          Array.isArray(profile.unresolved_inputs)
                            ? profile.unresolved_inputs.map(String)
                            : []
                        }
                      />
                      <h3>Пробелы нормативных оснований</h3>
                      <GapList
                        gaps={profileGaps.map(
                          (item) => item.code ?? "NORMATIVE_GAP",
                        )}
                      />
                    </>
                  ) : (
                    <p className="empty-state">
                      Применимый нормативный профиль ещё не сформирован.
                    </p>
                  )}
                </section>
              </div>
              <section className="panel">
                <h2>Пакеты работ</h2>
                {value.work_packages.length ? (
                  <div className="card-grid">
                    {value.work_packages.map((item) => (
                      <WorkPackageCard
                        key={String(item.work_package_id)}
                        item={item}
                        workspaceId={workspaceId}
                        modeSlug={mode}
                        evidenceIndex={evidenceIndex}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="empty-state">Пакеты работ ещё не определены.</p>
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
  modeSlug,
  evidenceIndex,
}: {
  item: Record<string, unknown>;
  workspaceId: string;
  modeSlug?: string | undefined;
  evidenceIndex: Record<string, Record<string, unknown>>;
}) {
  const packageValue = (item.package ?? {}) as Record<string, unknown>;
  const workType = (packageValue.work_type ?? {}) as Record<string, unknown>;
  const locators = Array.isArray(packageValue.source_locator_ids)
    ? packageValue.source_locator_ids
    : [];
  return (
    <article className="entity-card">
      <h3>{displayValue(workType.normalized, "Не определён")}</h3>
      <p>
        Исходные подтверждения:{" "}
        {locators.length
          ? locators.map((locator) => {
              const identity = String(locator);
              const evidence = evidenceIndex[identity];
              return (
                <Link
                  key={identity}
                  to={workspaceRouteFromSlug(
                    modeSlug,
                    workspaceId,
                    `/evidence/locators/${identity}`,
                  )}
                >
                  {evidence
                    ? `страница ${displayValue(evidence.locator_value)}`
                    : "открыть источник"}
                </Link>
              );
            })
          : "не указаны"}
      </p>
    </article>
  );
}

function EvidenceObject({
  value,
  workspaceId,
  modeSlug,
  evidenceIndex,
}: {
  value: Record<string, unknown>;
  workspaceId?: string;
  modeSlug?: string | undefined;
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
                "Нет результата",
              )}
            </dd>
            {item.raw_value !== undefined && (
              <dd className="muted">
                В источнике: {displayValue(item.raw_value)}
              </dd>
            )}
            {item.source_locator_id !== undefined && (
              <dd className="mono">
                {workspaceId ? (
                  <Link
                    to={workspaceRouteFromSlug(
                      modeSlug,
                      workspaceId,
                      `/evidence/locators/${locatorIdentity}`,
                    )}
                  >
                    Открыть исходный фрагмент
                    {evidenceIndex?.[locatorIdentity]
                      ? ""
                      : " (связь не разрешена)"}
                  </Link>
                ) : (
                  <>Исходный фрагмент: {displayValue(item.source_locator_id)}</>
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
      title="Нормативная база комплекса"
      lead="Состояние нормативных источников и профессиональных методик, используемых комплексом."
    >
      <QueryState query={status}>
        {(value) => (
          <>
            <section className="panel admin-summary">
              <h2>Общее состояние</h2>
              <p>
                Загружено проверенных нормативных редакций:{" "}
                {value.verified_normative_edition_count.toLocaleString("ru-RU")}
                . Активных методик:{" "}
                {value.active_playbook_count.toLocaleString("ru-RU")}.
              </p>
              <p>
                {value.knowledge_ready
                  ? "Нормативная база готова к использованию."
                  : "Часть нормативных источников и методик ещё требует подготовки."}
              </p>
            </section>
            <details className="panel technical-details">
              <summary>Технические сведения</summary>
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
              <section className="danger-panel technical-section">
                <h2>KnowledgeReady = {String(value.knowledge_ready)}</h2>
                <GapList gaps={value.blockers} />
              </section>
              <section className="technical-section">
                <h2>Fingerprints</h2>
                <pre>
                  {JSON.stringify(value.semantic_fingerprints, null, 2)}
                </pre>
              </section>
              <section className="technical-section">
                <h2>NTD Seed Remediation — exact denominator</h2>
                <QueryState query={ntdSeed}>
                  {(seed) => <NtdSeedStatusTable value={seed} />}
                </QueryState>
              </section>
            </details>
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
      title="Состояние комплекса"
      lead="Работоспособность развернутого контура и доступность его основных функций."
    >
      <QueryState query={capabilities}>
        {(value) => (
          <>
            <section className="panel admin-summary">
              <h2>Общее состояние</h2>
              <p>
                Комплекс доступен для разработки и проверки реализованных
                функций. Полная готовность к промышленной эксплуатации пока не
                заявлена.
              </p>
            </section>
            <details className="panel technical-details">
              <summary>Технические сведения</summary>
              <div className="split technical-section">
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
                <section className="panel">
                  <h2>Deployment</h2>
                  <dl>
                    <dt>Source commit</dt>
                    <dd className="mono">{value.deployment.source_commit}</dd>
                    <dt>Runtime profile</dt>
                    <dd>{value.deployment.runtime_profile}</dd>
                    <dt>Migration head</dt>
                    <dd className="mono">{value.deployment.migration_head}</dd>
                    <dt>Deployed at</dt>
                    <dd>{value.deployment.deployed_at ?? "not deployed"}</dd>
                    <dt>Frontend</dt>
                    <dd className="mono">
                      {value.deployment.frontend_build_digest ?? "not pinned"}
                    </dd>
                    <dt>OpenAPI</dt>
                    <dd className="mono">
                      {value.deployment.openapi_digest ?? "not pinned"}
                    </dd>
                  </dl>
                </section>
              </div>
            </details>
          </>
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
      {humanizeError(error)}
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
        <li key={gap}>{humanizeGap(gap)}</li>
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

function humanizeStatus(value: string) {
  const labels: Record<string, string> = {
    ACTIVE: "В работе",
    active: "Действует",
    complete: "Обработан",
    partial_with_capability_gap: "Требует дополнения",
    failed: "Ошибка",
    queued: "В очереди",
    leased: "Назначено исполнителю",
    running: "Выполняется",
    succeeded: "Завершено",
    cancelled: "Отменено",
    reconciliation_required: "Требует проверки",
    finalized: "Финализирован",
    generated_candidate: "Проект подготовлен",
    missing: "Отсутствует",
    blocked: "Заблокирован",
    required: "Требуется",
    conditional: "При определённых условиях",
    not_applicable: "Не применяется",
    unresolved: "Требует уточнения",
    approved: "Одобрено",
    print_ready: "Готово к печати",
    qualified: "Квалифицировано",
    unqualified: "Не квалифицировано",
    authoritative: "Официальное основание",
    verified: "Проверено",
  };
  return labels[value] ?? value.replaceAll("_", " ").toLowerCase();
}

function humanizeDocumentRole(value: string) {
  const labels: Record<string, string> = {
    register: "Реестр документов комплекта",
    "support.aosr": "Акт освидетельствования скрытых работ",
    aosr: "Акт освидетельствования скрытых работ",
    executive_scheme: "Исполнительная схема",
    quality_documents: "Документы о качестве материалов",
    attachment: "Приложение",
  };
  return labels[value.toLowerCase()] ?? value.replaceAll("_", " ");
}

function humanizeFieldKey(value: string) {
  const labels: Record<string, string> = {
    "work_type.classification": "Вид работы",
    work_type: "Вид работы",
    project_reference: "Ссылка на проект",
    organization: "Организация",
    object_name: "Наименование объекта",
    act_number: "Номер акта",
    act_date: "Дата акта",
  };
  return labels[value] ?? value.replaceAll(".", " · ").replaceAll("_", " ");
}

function humanizeReadiness(value: string) {
  if (["READY", "COMPLETE"].includes(value)) return "Готово";
  if (["PARTIAL", "FOUNDATION_ONLY"].includes(value))
    return "Доступно частично";
  return "Требует подготовки";
}

function humanizeGap(value: string) {
  const labels: Record<string, string> = {
    WORK_REQUIREMENT_MATRIX_UNAVAILABLE: "Матрица работ ещё не сформирована.",
    VERIFIED_NTD_SUBSET: "Не все нормативные основания проверены.",
    TEMPLATE_NOT_PRODUCTION_QUALIFIED:
      "Форма документа ещё не квалифицирована для выпуска.",
    EXECUTIVE_SCHEME_OUTPUT_BLOCKED:
      "Исполнительная схема не может быть подготовлена без подтверждённой геометрии.",
    QUALITY_DOCUMENTS_MISSING: "Документы о качестве материалов отсутствуют.",
    OCR_REQUIRED: "Для части страниц требуется распознавание.",
  };
  return (
    labels[value] ?? "Требуется дополнительная проверка или исходные данные."
  );
}

function humanizeError(error: unknown) {
  if (!(error instanceof Error)) return "Не удалось выполнить запрос.";
  if (/401|session|unauthor/i.test(error.message))
    return "Сеанс завершён. Войдите снова.";
  if (/403|forbidden/i.test(error.message))
    return "Недостаточно прав для выполнения действия.";
  return "Не удалось выполнить действие. Повторите попытку или обратитесь к администратору.";
}
