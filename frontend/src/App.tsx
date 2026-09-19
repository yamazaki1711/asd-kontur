import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DragEvent,
  KeyboardEvent,
  ReactNode,
  SyntheticEvent,
  useEffect,
  useState,
} from "react";
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
import { mergeFieldResolutionRows } from "./supportFieldRows";
import { PdfEvidenceViewer } from "./viewer/PdfEvidenceViewer";

type Workspace = components["schemas"]["WorkspaceView"];
type Document = components["schemas"]["DocumentView"];
type Job = components["schemas"]["JobView"];
type NtdSeedStatus = components["schemas"]["NtdSeedStatusView"];
type NtdSeedIdentity = components["schemas"]["NtdSeedIdentityView"];
type SupportProduction = components["schemas"]["SupportProductionView"];
type AuditExpectedActualPreflight =
  components["schemas"]["AuditExpectedActualPreflightView"];
type AuditReportProjection =
  components["schemas"]["AuditReportProjectionView"];
type AuditPreflightItem = {
  item_key: string;
  work_package_id: string;
  document_type: string;
  preflight_state: string;
  membership_count: number;
  membership_states: string[];
  evidence_refs: string[];
  gaps: string[];
  required_correction: string;
  practical_consequence: string;
};
type RestorationRecoveryPlan =
  components["schemas"]["RestorationRecoveryPlanView"];
type PilotResult = components["schemas"]["PilotResultView"];
type AssistantConversation = components["schemas"]["AssistantConversationView"];
type AssistantMessage = components["schemas"]["AssistantMessageView"];
type ConstructionConsultantConversation =
  components["schemas"]["ConstructionConsultantConversationView"];
type ConstructionConsultantMessage =
  components["schemas"]["ConstructionConsultantMessageView"];

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

const EXPECTED_SOURCE_DOCUMENTS: Record<ModeName, string[]> = {
  Tender: [
    "Договор и приложения",
    "ПД и РД",
    "Ведомости объёмов работ и сметы",
    "Техническое задание",
    "Требования и регламенты заказчика",
  ],
  Support: [
    "ПД и РД",
    "Договорные и организационно-технологические документы",
    "Сведения о работах и материалах",
    "Имеющаяся исполнительная документация",
    "Журналы, акты, схемы и документы о качестве",
  ],
  Audit: [
    "Проверяемый комплект документации",
    "Исходные ПД и РД",
    "Договор и требования заказчика",
    "Фактические документы и реестры",
    "Сведения об объёме и границах аудита",
  ],
  Restoration: [
    "Сохранившаяся исполнительная документация",
    "Журналы и акты",
    "Исполнительные схемы",
    "Документы о качестве",
    "Подтверждённые сведения о выполненных работах",
  ],
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

function primaryModeOutputRoute(mode: ModeName, workspaceId: string) {
  const suffix =
    mode === "Support"
      ? "/support-id"
      : mode === "Audit"
        ? "/audit-preflight"
        : mode === "Restoration"
          ? "/recovery-plan"
          : "/project-understanding";
  return workspaceRoute(mode, workspaceId, suffix);
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
          <Route
            path="/modes/:mode/workspaces/:workspaceId/audit-preflight"
            element={<AuditExpectedActualPreflightPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/audit-report"
            element={<AuditReportProjectionPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/recovery-plan"
            element={<RestorationRecoveryPlanPage />}
          />
          <Route
            path="/modes/:mode/workspaces/:workspaceId/result"
            element={<PilotResultPage />}
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
  const [assistantOpen, setAssistantOpen] = useState(() =>
    workspaceId
      ? window.localStorage.getItem(`asd-assistant-open-${workspaceId}`) ===
        "true"
      : false,
  );
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
  useEffect(() => {
    if (workspaceId) {
      window.localStorage.setItem(
        `asd-assistant-open-${workspaceId}`,
        String(assistantOpen),
      );
    }
  }, [assistantOpen, workspaceId]);
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
              <button
                className="assistant-launch"
                type="button"
                aria-expanded={assistantOpen}
                onClick={() => setAssistantOpen((value) => !value)}
              >
                Инженерный помощник
              </button>
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
            label="Модель объекта"
          />
          <NavItem
            to={`${workspaceBase}/work-matrix`}
            label="Работы и требования"
          />
          <NavItem to={`${workspaceBase}/result`} label="Результат режима" />
          {mode === "Support" && (
            <NavItem
              to={`${workspaceBase}/support-id`}
              label="Исполнительная документация"
            />
          )}
          {mode === "Audit" && (
            <>
              <NavItem
                to={`${workspaceBase}/audit-preflight`}
                label="Предварительная сверка"
              />
              <NavItem
                to={`${workspaceBase}/audit-report`}
                label="Отчёт независимого аудита"
              />
            </>
          )}
          {mode === "Restoration" && (
            <NavItem
              to={`${workspaceBase}/recovery-plan`}
              label="План восстановления"
            />
          )}
          <NavItem to={`${workspaceBase}/evidence`} label="Источники" />
        </aside>
      )}
      <main className="content">
        <Outlet />
      </main>
      {workspaceId && mode && assistantOpen && (
        <AssistantPanel
          workspaceId={workspaceId}
          mode={mode}
          onClose={() => setAssistantOpen(false)}
        />
      )}
    </div>
  );
}

function AssistantPanel({
  workspaceId,
  mode,
  onClose,
}: {
  workspaceId: string;
  mode: ModeName;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(() =>
    window.localStorage.getItem(`asd-assistant-conversation-${workspaceId}`),
  );
  const [question, setQuestion] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [streamSources, setStreamSources] = useState<Record<string, unknown>[]>(
    [],
  );
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const conversations = useQuery({
    queryKey: ["assistant-conversations", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/assistant/conversations",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  const createConversation = useMutation({
    mutationFn: async (title?: string) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/assistant/conversations",
        {
          params: { path: { workspace_id: workspaceId } },
          body: { title: title || "Новый диалог" },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async (value) => {
      setConversationId(value.conversation_id);
      window.localStorage.setItem(
        `asd-assistant-conversation-${workspaceId}`,
        value.conversation_id,
      );
      setStreamingText("");
      setStreamSources([]);
      await queryClient.invalidateQueries({
        queryKey: ["assistant-conversations", workspaceId],
      });
    },
  });
  const effectiveConversationId =
    conversationId ?? conversations.data?.[0]?.conversation_id ?? null;
  const messages = useQuery({
    queryKey: ["assistant-messages", workspaceId, effectiveConversationId],
    enabled: Boolean(effectiveConversationId),
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/assistant/conversations/{conversation_id}/messages",
        {
          params: {
            path: {
              workspace_id: workspaceId,
              conversation_id: effectiveConversationId ?? "",
            },
          },
        },
      );
      return requireData(data, error);
    },
  });
  const ask = useMutation({
    mutationFn: async ({
      identity,
      text,
    }: {
      identity: string;
      text: string;
    }) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/assistant/conversations/{conversation_id}/turns",
        {
          params: {
            path: {
              workspace_id: workspaceId,
              conversation_id: identity,
            },
          },
          body: { mode, question: text },
        },
      );
      return requireData(data, error);
    },
    onSuccess: (turn) => {
      setQuestion("");
      setStreamingText("");
      setStreamSources([]);
      setStreamError(null);
      setActiveTurn(turn.turn_id);
      const events = new EventSource(
        `/api/v1/workspaces/${workspaceId}/assistant/turns/${turn.turn_id}/events`,
      );
      events.addEventListener("delta", (event) => {
        const value = JSON.parse((event as MessageEvent<string>).data) as {
          text?: string;
        };
        setStreamingText((current) => current + (value.text ?? ""));
      });
      events.addEventListener("source", (event) => {
        const value = JSON.parse(
          (event as MessageEvent<string>).data,
        ) as Record<string, unknown>;
        setStreamSources((current) => [...current, value]);
      });
      const finish = () => {
        events.close();
        setActiveTurn(null);
        void queryClient.invalidateQueries({
          queryKey: [
            "assistant-messages",
            workspaceId,
            effectiveConversationId,
          ],
        });
      };
      events.addEventListener("completed", finish);
      events.addEventListener("failed", (event) => {
        const value = JSON.parse((event as MessageEvent<string>).data) as {
          message?: string;
        };
        setStreamError(value.message ?? "Помощник временно недоступен.");
        finish();
      });
      events.addEventListener("reconciliation_required", (event) => {
        const value = JSON.parse((event as MessageEvent<string>).data) as {
          message?: string;
        };
        setStreamError(value.message ?? "Помощник временно недоступен.");
        finish();
      });
      events.addEventListener("cancelled", (event) => {
        const value = JSON.parse((event as MessageEvent<string>).data) as {
          message?: string;
        };
        setStreamError(value.message ?? "Формирование ответа остановлено.");
        finish();
      });
      events.onerror = () => {
        if (events.readyState === EventSource.CLOSED) finish();
      };
    },
  });
  const stop = useMutation({
    mutationFn: async () => {
      if (!activeTurn) return;
      const { error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/assistant/turns/{turn_id}/cancel",
        {
          params: {
            path: { workspace_id: workspaceId, turn_id: activeTurn },
          },
          body: { confirmation: "STOP_ASSISTANT_RESPONSE" },
        },
      );
      if (error) throw new Error("assistant_stop_failed");
    },
  });
  const submit = async () => {
    const text = question.trim();
    if (!text || activeTurn) return;
    let identity = effectiveConversationId;
    if (!identity) {
      const created = await createConversation.mutateAsync(text.slice(0, 120));
      identity = created.conversation_id;
    }
    ask.mutate({ identity, text });
  };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };
  const values = (messages.data ?? []) as AssistantMessage[];
  return (
    <aside
      className="assistant-panel"
      aria-label="Инженерный помощник"
      data-testid="assistant-panel"
    >
      <header className="assistant-header">
        <div>
          <strong>Инженерный помощник</strong>
          <small>{MODE_DEFINITIONS[mode].title}</small>
        </div>
        <button className="ghost" type="button" onClick={onClose}>
          Закрыть
        </button>
      </header>
      <div className="assistant-toolbar">
        <label>
          Диалог
          <select
            value={effectiveConversationId ?? ""}
            onChange={(event) => {
              setConversationId(event.target.value || null);
              if (event.target.value) {
                window.localStorage.setItem(
                  `asd-assistant-conversation-${workspaceId}`,
                  event.target.value,
                );
              }
            }}
          >
            <option value="">Новый диалог</option>
            {(conversations.data ?? []).map((item: AssistantConversation) => (
              <option key={item.conversation_id} value={item.conversation_id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          type="button"
          onClick={() => {
            setConversationId("");
            window.localStorage.removeItem(
              `asd-assistant-conversation-${workspaceId}`,
            );
            setStreamingText("");
            setStreamSources([]);
            setStreamError(null);
          }}
        >
          Новый диалог
        </button>
      </div>
      <div className="assistant-messages" aria-live="polite">
        {values.length === 0 && !streamingText && (
          <div className="assistant-empty">
            <strong>Задайте профессиональный вопрос</strong>
            <p>
              Помощник использует нормативные и методические материалы, а также
              сведения открытого объекта строительства.
            </p>
          </div>
        )}
        {values.map((message) => (
          <AssistantMessageCard
            key={message.message_id}
            message={message}
            {...(message.role === "user" ? { onRepeat: setQuestion } : {})}
          />
        ))}
        {(activeTurn || streamingText) && (
          <article className="assistant-message assistant-message-answer">
            <strong>Ответ</strong>
            <div className="assistant-answer">
              {streamingText || "Подбираю сведения и источники…"}
            </div>
            {streamSources.length > 0 && (
              <AssistantSources sources={streamSources} />
            )}
          </article>
        )}
        {streamError && (
          <div className="notice error-notice">{streamError}</div>
        )}
      </div>
      <footer className="assistant-composer">
        <label htmlFor="assistant-question">Ваш вопрос</label>
        <textarea
          id="assistant-question"
          rows={3}
          value={question}
          placeholder="Например: какие документы нужны для предъявления этой работы?"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={keyDown}
          disabled={Boolean(activeTurn)}
        />
        <div className="assistant-composer-actions">
          {activeTurn ? (
            <button
              type="button"
              className="secondary"
              onClick={() => stop.mutate()}
            >
              Остановить
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!question.trim()}
            >
              Отправить
            </button>
          )}
          <small>Enter — отправить, Shift+Enter — новая строка</small>
        </div>
      </footer>
    </aside>
  );
}

function AssistantMessageCard({
  message,
  onRepeat,
}: {
  message: AssistantMessage;
  onRepeat?: (value: string) => void;
}) {
  return (
    <article
      className={`assistant-message ${
        message.role === "user"
          ? "assistant-message-question"
          : "assistant-message-answer"
      }`}
    >
      <strong>{message.role === "user" ? "Вы" : "Ответ"}</strong>
      <div className="assistant-answer">{message.content}</div>
      {message.sources.length > 0 && (
        <AssistantSources sources={message.sources} />
      )}
      {message.action_proposals.length > 0 && (
        <div className="assistant-proposals" aria-label="Предложенные действия">
          {message.action_proposals.map((proposal, index) => (
            <Link
              className="secondary"
              key={`${displayValue(proposal.kind)}-${String(index)}`}
              to={displayValue(proposal.href, "/modes")}
            >
              {displayValue(proposal.label, "Открыть результат")}
            </Link>
          ))}
        </div>
      )}
      <div className="assistant-message-actions">
        {message.role === "assistant" && (
          <button
            className="text-action"
            type="button"
            onClick={() => void navigator.clipboard.writeText(message.content)}
          >
            Копировать
          </button>
        )}
        {onRepeat && (
          <button
            className="text-action"
            type="button"
            onClick={() => onRepeat(message.content)}
          >
            Повторить вопрос
          </button>
        )}
      </div>
    </article>
  );
}

function AssistantSources({ sources }: { sources: Record<string, unknown>[] }) {
  return (
    <details className="assistant-sources" open>
      <summary>Источники ({sources.length})</summary>
      <ol>
        {sources.map((source, index) => (
          <li key={`${displayValue(source.source_id)}-${String(index)}`}>
            <a
              href={displayValue(source.href, "#")}
              target="_blank"
              rel="noreferrer"
            >
              {displayValue(source.title, "Источник")} ·{" "}
              {displayValue(source.locator_label)}
            </a>
            {source.edition ? (
              <span>Редакция: {displayValue(source.edition)}</span>
            ) : null}
            {source.edition_currency_notice ? (
              <small>{displayValue(source.edition_currency_notice)}</small>
            ) : null}
            {source.fragment ? (
              <blockquote>{displayValue(source.fragment)}</blockquote>
            ) : null}
          </li>
        ))}
      </ol>
    </details>
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
        {MODES.map((mode) => {
          const titleId = `mode-card-${MODE_DEFINITIONS[mode].slug}-title`;
          return (
            <Link
              aria-labelledby={titleId}
              className="mode-card"
              key={mode}
              to={`/modes/${MODE_DEFINITIONS[mode].slug}/workspaces`}
            >
              <span className="mode-number">0{MODES.indexOf(mode) + 1}</span>
              <h2 id={titleId}>{MODE_DEFINITIONS[mode].title}</h2>
              <p>{MODE_DEFINITIONS[mode].purpose}</p>
              <h3>Результаты работы</h3>
              <p>{MODE_DEFINITIONS[mode].results}</p>
            </Link>
          );
        })}
      </div>
      <ConstructionConsultantPanel />
    </Page>
  );
}

function ConstructionConsultantPanel() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(() =>
    window.localStorage.getItem("asd-construction-consultant-conversation"),
  );
  const [question, setQuestion] = useState("");
  const conversations = useQuery({
    queryKey: ["construction-consultant-conversations"],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/construction-consultant/conversations",
      );
      return requireData(data, error);
    },
  });
  const effectiveConversationId =
    conversationId ?? conversations.data?.[0]?.conversation_id ?? null;
  const messages = useQuery({
    queryKey: ["construction-consultant-messages", effectiveConversationId],
    enabled: Boolean(effectiveConversationId),
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/construction-consultant/conversations/{conversation_id}/messages",
        {
          params: { path: { conversation_id: effectiveConversationId ?? "" } },
        },
      );
      return requireData(data, error);
    },
  });
  const createConversation = useMutation({
    mutationFn: async (title: string) => {
      const { data, error } = await api.POST(
        "/api/v1/construction-consultant/conversations",
        { body: { title } },
      );
      return requireData(data, error);
    },
    onSuccess: async (value) => {
      setConversationId(value.conversation_id);
      window.localStorage.setItem(
        "asd-construction-consultant-conversation",
        value.conversation_id,
      );
      await queryClient.invalidateQueries({
        queryKey: ["construction-consultant-conversations"],
      });
    },
  });
  const ask = useMutation({
    mutationFn: async ({
      identity,
      text,
    }: {
      identity: string;
      text: string;
    }) => {
      const { data, error } = await api.POST(
        "/api/v1/construction-consultant/conversations/{conversation_id}/questions",
        {
          params: { path: { conversation_id: identity } },
          body: { request_id: crypto.randomUUID(), question: text },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      setQuestion("");
      await queryClient.invalidateQueries({
        queryKey: ["construction-consultant-messages", effectiveConversationId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["construction-consultant-conversations"],
      });
    },
  });
  const submit = async () => {
    const text = question.trim();
    if (!text || ask.isPending) return;
    let identity = effectiveConversationId;
    if (!identity) {
      const created = await createConversation.mutateAsync(text.slice(0, 120));
      identity = created.conversation_id;
    }
    ask.mutate({ identity, text });
  };
  const values = (messages.data ?? []) as ConstructionConsultantMessage[];
  return (
    <section
      className="construction-consultant"
      aria-labelledby="construction-consultant-title"
    >
      <div className="construction-consultant-heading">
        <div>
          <p className="eyebrow">Общие профессиональные знания</p>
          <h2 id="construction-consultant-title">Строительный консультант</h2>
          <p>
            Вопрос не привязан к объекту. Ответ опирается на методические и
            нормативные материалы; инженерная оценка всегда обозначается
            отдельно от подтверждённого факта.
          </p>
        </div>
        <label>
          Диалог
          <select
            value={effectiveConversationId ?? ""}
            onChange={(event) => {
              const next = event.target.value || null;
              setConversationId(next);
              if (next) {
                window.localStorage.setItem(
                  "asd-construction-consultant-conversation",
                  next,
                );
              }
            }}
          >
            <option value="">Новый диалог</option>
            {(conversations.data ?? []).map(
              (item: ConstructionConsultantConversation) => (
                <option key={item.conversation_id} value={item.conversation_id}>
                  {item.title}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      <div className="construction-consultant-history" aria-live="polite">
        {values.length === 0 ? (
          <p className="construction-consultant-empty">
            Например: «Как организовать входной контроль материалов?»
          </p>
        ) : (
          values.map((message) => (
            <article
              className={`construction-consultant-message construction-consultant-message-${message.role}`}
              key={message.message_id}
            >
              <strong>{message.role === "user" ? "Вы" : "Ответ"}</strong>
              <div>{message.content}</div>
              {message.sources.length > 0 ? (
                <details className="construction-consultant-sources">
                  <summary>Основания ответа ({message.sources.length})</summary>
                  <ol>
                    {message.sources.map((source, index) => {
                      const href = displayValue(source.href, "");
                      const title = displayValue(source.title, "Источник");
                      return (
                        <li
                          key={`${displayValue(source.source_id)}-${String(index)}`}
                        >
                          {href ? (
                            <a href={href} target="_blank" rel="noreferrer">
                              {title}
                            </a>
                          ) : (
                            <span>{title}</span>
                          )}
                          <small>
                            {displayValue(source.locator, "Локатор не указан")}
                          </small>
                          {source.fragment ? (
                            <blockquote>
                              {displayValue(source.fragment)}
                            </blockquote>
                          ) : null}
                        </li>
                      );
                    })}
                  </ol>
                </details>
              ) : null}
            </article>
          ))
        )}
        {ask.isPending ? (
          <p className="construction-consultant-pending">Формирую ответ…</p>
        ) : null}
        {ask.isError ? (
          <p className="notice error-notice">
            {ask.error instanceof Error
              ? ask.error.message
              : "Консультант временно недоступен."}
          </p>
        ) : null}
      </div>
      <div className="construction-consultant-composer">
        <label htmlFor="construction-consultant-question">Ваш вопрос</label>
        <textarea
          id="construction-consultant-question"
          rows={3}
          value={question}
          placeholder="Задайте общий вопрос по строительным работам, контролю или исполнительной документации"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          disabled={ask.isPending || createConversation.isPending}
        />
        <div>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={
              !question.trim() || ask.isPending || createConversation.isPending
            }
          >
            Отправить вопрос
          </button>
          <button
            className="secondary"
            type="button"
            onClick={() => {
              setConversationId(null);
              window.localStorage.removeItem(
                "asd-construction-consultant-conversation",
              );
            }}
          >
            Новый диалог
          </button>
        </div>
      </div>
    </section>
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
        {MODES.map((mode) => {
          const titleId = `legacy-mode-card-${MODE_DEFINITIONS[mode].slug}-title`;
          return (
            <Link
              aria-labelledby={titleId}
              className="mode-card"
              key={mode}
              to={workspaceRoute(mode, workspaceId, suffix)}
            >
              <h2 id={titleId}>{MODE_DEFINITIONS[mode].title}</h2>
              <p>{MODE_DEFINITIONS[mode].purpose}</p>
            </Link>
          );
        })}
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
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const normalizedMode = modeFromSlug(mode) ?? "Tender";
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
    mutationFn: async (files: File[]) => {
      const form = new FormData();
      const relative: string[] = [];
      for (const file of files) {
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
      setSelectedFiles([]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] }),
        queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] }),
      ]);
    },
  });
  const addFiles = (files: FileList | File[]) => {
    setSelectedFiles((current) => {
      const values = [...current];
      const keys = new Set(
        current.map(
          (file) =>
            `${file.webkitRelativePath || file.name}:${String(file.size)}:${String(file.lastModified)}`,
        ),
      );
      for (const file of Array.from(files)) {
        const key = `${file.webkitRelativePath || file.name}:${String(file.size)}:${String(file.lastModified)}`;
        if (!keys.has(key)) {
          keys.add(key);
          values.push(file);
        }
      }
      return values;
    });
  };
  const dropFiles = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    addFiles(event.dataTransfer.files);
  };
  const selectedBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
  return (
    <Page
      title="Исходные документы"
      lead="Добавьте документы без предварительной ручной сортировки. Неполный комплект можно дополнять позднее."
    >
      <section className="split intake-start">
        <article className="panel">
          <h2>Что обычно требуется</h2>
          <p>Для режима «{MODE_DEFINITIONS[normalizedMode].title}»:</p>
          <ul>
            {EXPECTED_SOURCE_DOCUMENTS[normalizedMode].map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="muted-copy">
            Перечень служит подсказкой и не препятствует приёму неполного
            комплекта.
          </p>
        </article>
        <article className="panel">
          <h2>Добавить исходные документы</h2>
          <div
            className={`drop-zone${dragActive ? " drag-active" : ""}`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragActive(true);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragActive(false)}
            onDrop={dropFiles}
          >
            <strong>Перетащите файлы сюда</strong>
            <span>или выберите файлы, папку либо архив ZIP</span>
            <div className="upload-actions">
              <label className="upload-button">
                Выбрать файлы
                <input
                  hidden
                  type="file"
                  multiple
                  accept=".pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.tif,.tiff,.zip"
                  onChange={(event) =>
                    event.target.files && addFiles(event.target.files)
                  }
                />
              </label>
              <label className="upload-button secondary">
                Выбрать папку
                <input
                  hidden
                  type="file"
                  multiple
                  {...({ webkitdirectory: "", directory: "" } as object)}
                  onChange={(event) =>
                    event.target.files && addFiles(event.target.files)
                  }
                />
              </label>
            </div>
          </div>
        </article>
      </section>
      {selectedFiles.length > 0 && (
        <section className="panel selected-upload" aria-live="polite">
          <div className="entity-heading">
            <div>
              <h2>Подготовлено к загрузке</h2>
              <p>
                {selectedFiles.length} файлов · {formatBytes(selectedBytes)}
              </p>
            </div>
            <button
              type="button"
              onClick={() => upload.mutate(selectedFiles)}
              disabled={upload.isPending}
            >
              Начать загрузку
            </button>
          </div>
          <ul className="selected-file-list">
            {selectedFiles.map((file, index) => (
              <li
                key={`${file.webkitRelativePath || file.name}:${String(file.size)}:${String(file.lastModified)}`}
              >
                <span>
                  <strong>{file.name}</strong>
                  <small>
                    {file.webkitRelativePath || file.name} ·{" "}
                    {formatBytes(file.size)}
                  </small>
                </span>
                <button
                  type="button"
                  className="ghost"
                  aria-label={`Исключить ${file.name}`}
                  onClick={() =>
                    setSelectedFiles((items) =>
                      items.filter((_, itemIndex) => itemIndex !== index),
                    )
                  }
                >
                  Исключить
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="panel toolbar">
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
          Файлы загружаются и регистрируются. Уже принятые данные не будут
          потеряны при повторе…
        </InfoNotice>
      )}
      {upload.isError && <ErrorNotice error={upload.error} />}
      {upload.isSuccess && (
        <InfoNotice>
          Принято новых файлов: {upload.data.accepted_document_ids.length}.
          Повторных файлов: {upload.data.duplicate_document_ids.length}. Не
          поддержано или отклонено: {upload.data.rejected_count}.
        </InfoNotice>
      )}
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
            <th>Тип / размер</th>
            <th>Приём</th>
            <th>Обработка</th>
            <th>Страниц</th>
            <th>Сведения</th>
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
                {document.media_type}
                <small>{formatBytes(document.size_bytes)}</small>
              </td>
              <td>
                <StatusPill>
                  {humanizeStatus(document.admission_status)}
                </StatusPill>
              </td>
              <td>
                <StatusPill
                  tone={document.capability_gaps.length ? "warning" : "default"}
                >
                  {humanizeStatus(document.extraction_status)}
                </StatusPill>
                {document.capability_gaps.map((gap) => (
                  <small key={gap}>{humanizeGap(gap)}</small>
                ))}
              </td>
              <td>{document.page_count ?? "—"}</td>
              <td>
                <span>Версия {document.version}</span>
                <small>
                  <Link
                    to={workspaceRouteFromSlug(modeSlug, workspaceId, "/jobs")}
                  >
                    Ход обработки
                  </Link>
                </small>
              </td>
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
              <dt>Страница и область</dt>
              <dd>
                {value.locator.page_number} / {value.locator.region.join(", ")}
              </dd>
              <dt>Способ получения</dt>
              <dd>
                {humanizeExtractionMethod(value.locator.extraction_method)}
              </dd>
              <dt>Состояние сведения</dt>
              <dd>{humanizeStatus(value.candidate_fact_status)}</dd>
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
        {
          params: {
            path: { workspace_id: workspaceId },
            query: { effective_only: true },
          },
        },
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
      lead="Текущие эффективные задания обработки. Исторические попытки сохраняются отдельно и не заменяют актуальный статус."
    >
      <QueryState query={jobs} empty="Заданий обработки пока нет.">
        {(items) => <JobTable jobs={items} workspaceId={workspaceId} />}
      </QueryState>
    </Page>
  );
}

function JobTable({ jobs, workspaceId }: { jobs: Job[]; workspaceId: string }) {
  const queryClient = useQueryClient();
  const refreshJobs = () =>
    queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] });
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
    onSuccess: refreshJobs,
  });
  const pause = useMutation({
    mutationFn: async (jobId: string) => {
      const { error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/pause",
        { params: { path: { workspace_id: workspaceId, job_id: jobId } } },
      );
      if (error) throw new Error("job_pause_failed");
    },
    onSuccess: refreshJobs,
  });
  const resume = useMutation({
    mutationFn: async (jobId: string) => {
      const { error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/resume",
        { params: { path: { workspace_id: workspaceId, job_id: jobId } } },
      );
      if (error) throw new Error("job_resume_failed");
    },
    onSuccess: refreshJobs,
  });
  const retry = useMutation({
    mutationFn: async (jobId: string) => {
      const { error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/retry",
        { params: { path: { workspace_id: workspaceId, job_id: jobId } } },
      );
      if (error) throw new Error("job_retry_failed");
    },
    onSuccess: refreshJobs,
  });
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Вид обработки</th>
            <th>Состояние</th>
            <th>Семантические пакеты</th>
            <th>Попытки</th>
            <th>Причина ошибки</th>
            <th>Результат</th>
            <th>Действие</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.job_id}>
              <td>{humanizeJobKind(job.job_kind)}</td>
              <td>
                <StatusPill
                  tone={
                    job.lease_expired ||
                    job.state === "failed" ||
                    job.state === "reconciliation_required"
                      ? "danger"
                      : "default"
                  }
                >
                  {job.lease_expired
                    ? "Исполнитель недоступен; восстановление ожидается"
                    : humanizeStatus(job.state)}
                </StatusPill>
              </td>
              <td>
                {job.progress_message_code ===
                  "engineering_semantic_batch_accepted" &&
                Number.isInteger(job.progress_current) &&
                Number.isInteger(job.progress_total)
                  ? `${String(job.progress_current)} / ${String(job.progress_total)}`
                  : "—"}
              </td>
              <td>
                {job.attempt_count} / {job.max_attempts}
              </td>
              <td>{job.typed_failure_code ?? "—"}</td>
              <td className="mono truncate">
                {job.terminal_receipt_id ?? "—"}
              </td>
              <td>
                <div className="inline-actions">
                  {job.state === "queued" && (
                    <button
                      className="ghost"
                      onClick={() => pause.mutate(job.job_id)}
                    >
                      Приостановить
                    </button>
                  )}
                  {job.state === "paused" && (
                    <button
                      className="ghost"
                      onClick={() => resume.mutate(job.job_id)}
                    >
                      Продолжить
                    </button>
                  )}
                  {["queued", "paused", "leased", "running"].includes(
                    job.state,
                  ) && (
                    <button
                      className="ghost"
                      onClick={() => cancel.mutate(job.job_id)}
                    >
                      Отменить
                    </button>
                  )}
                  {["failed", "cancelled", "reconciliation_required"].includes(
                    job.state,
                  ) && (
                    <button
                      className="ghost"
                      onClick={() => retry.mutate(job.job_id)}
                    >
                      Повторить
                    </button>
                  )}
                </div>
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
      title="Источники"
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
  const { mode } = useParams();
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
      title="Работы и требования"
      lead="Структура работ объекта и связанные требования к контролю и документам."
    >
      <QueryState query={understanding}>
        {(view) => {
          const matrixValue = (view.matrix.matrix ?? {}) as Record<
            string,
            unknown
          >;
          const rows = Array.isArray(matrixValue.rows)
            ? (matrixValue.rows as Record<string, unknown>[])
            : [];
          const packageNames = new Map(
            view.work_packages.map((item) => {
              const packageValue = (item.package ?? {}) as Record<
                string,
                unknown
              >;
              const workType = (packageValue.work_type ?? {}) as Record<
                string,
                unknown
              >;
              return [
                String(item.work_package_id),
                displayValue(workType.normalized, "Работа требует уточнения"),
              ];
            }),
          );
          return rows.length ? (
            <div className="matrix-cards">
              {rows.map((row) => {
                const locators = Array.isArray(row.workspace_facts)
                  ? row.workspace_facts.map(String)
                  : [];
                const gaps = Array.isArray(row.gaps)
                  ? row.gaps.map((gap) => humanizeGap(String(gap)))
                  : [];
                return (
                  <article className="panel" key={String(row.work_package_id)}>
                    <div className="entity-heading">
                      <h2>
                        {packageNames.get(String(row.work_package_id)) ??
                          "Работа требует уточнения"}
                      </h2>
                      <StatusPill tone={row.complete ? "default" : "warning"}>
                        {row.complete ? "Сформировано" : "Требует дополнения"}
                      </StatusPill>
                    </div>
                    <p>
                      Требования к контролю и документам формируются из общей
                      модели объекта. Неподтверждённые основания остаются
                      отдельными пробелами.
                    </p>
                    {locators.length > 0 && (
                      <div className="source-links">
                        <strong>Источники:</strong>
                        {locators.map((locator, index) => (
                          <Link
                            key={locator}
                            to={workspaceRouteFromSlug(
                              mode,
                              workspaceId,
                              `/evidence/locators/${locator}`,
                            )}
                          >
                            Исходный фрагмент {index + 1}
                          </Link>
                        ))}
                      </div>
                    )}
                    {gaps.length > 0 && <GapList gaps={gaps} />}
                  </article>
                );
              })}
              <Link
                className="button-link secondary"
                to={`${workspaceRouteFromSlug(mode, workspaceId, "/project-understanding")}?section=matrix`}
              >
                Открыть подробную модель объекта
              </Link>
            </div>
          ) : (
            <section className="panel empty-state">
              <p>Матрица ещё не сформирована.</p>
              <Link
                className="button-link"
                to={workspaceRouteFromSlug(
                  mode,
                  workspaceId,
                  "/project-understanding",
                )}
              >
                Перейти к модели объекта
              </Link>
            </section>
          );
        }}
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

function AuditExpectedActualPreflightPage() {
  const { workspaceId = "" } = useParams();
  const preflight = useQuery({
    queryKey: ["audit-expected-actual-preflight", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/audit/expected-actual-preflight",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  return (
    <Page
      title="Предварительная сверка комплекта"
      lead="Сопоставление требований матрицы с составом сформированного комплекта. Это не заменяет независимый аудит документов."
    >
      <QueryState query={preflight}>
        {(value) => (
          <AuditExpectedActualPreflightBody
            value={value}
            workspaceId={workspaceId}
          />
        )}
      </QueryState>
    </Page>
  );
}

function AuditReportProjectionPage() {
  const { workspaceId = "" } = useParams();
  const report = useQuery({
    queryKey: ["audit-report-projection", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/audit/reports/latest",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  return (
    <Page
      title="Отчёт независимого аудита"
      lead="Неизменяемый отчёт по точной версии состава документов, доказательствам и запросам на исправление."
    >
      <QueryState query={report}>
        {(value) => <AuditReportProjectionBody value={value} workspaceId={workspaceId} />}
      </QueryState>
    </Page>
  );
}

function AuditReportProjectionBody({
  value,
  workspaceId,
}: {
  value: AuditReportProjection;
  workspaceId: string;
}) {
  const gaps = value.gaps ?? [];
  if (value.status === "not_published") {
    return (
      <InfoNotice>
        Независимый отчёт ещё не опубликован. Предварительная сверка не заменяет
        аудит содержания, подписей и приложений.
        <GapList gaps={gaps} />
      </InfoNotice>
    );
  }
  const ptoPayload = (value.pto?.projection_payload ?? {}) as Record<
    string,
    unknown
  >;
  const report = (ptoPayload.report ?? {}) as Record<string, unknown>;
  const deltas = Array.isArray(ptoPayload.deltas)
    ? (ptoPayload.deltas as Array<Record<string, unknown>>)
    : [];
  const requests = Array.isArray(ptoPayload.action_requests)
    ? (ptoPayload.action_requests as Array<Record<string, unknown>>)
    : [];
  return (
    <>
      <InfoNotice>
        Это опубликованная проекция канонического отчёта. Она не изменяет
        исходные записи аудита и не подтверждает устранение замечаний без
        отдельного доказательства.
      </InfoNotice>
      <a
        className="button-link secondary"
        href={`/api/v1/workspaces/${workspaceId}/audit/reports/latest.csv`}
      >
        Скачать таблицу отчёта
      </a>
      <section className="metrics" aria-label="Состояние независимого аудита">
        <Metric label="Версия отчёта" value={Number(report.version ?? 0)} />
        <Metric
          label="Нерешённых кодов"
          value={Array.isArray(report.unresolved_codes) ? report.unresolved_codes.length : 0}
        />
        <Metric label="Запросов на исправление" value={requests.length} />
      </section>
      <section className="panel">
        <h2>Основание и результат</h2>
        <p>
          Статус: {humanizeStatus(
            typeof report.outcome === "string" ? report.outcome : "unknown",
          )}
        </p>
        <GapList
          gaps={Array.isArray(report.unresolved_codes) ? report.unresolved_codes.map(String) : []}
        />
      </section>
      <section className="panel">
        <h2>Состояние проверок</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Контур</th><th>Состояния</th><th>Нерешённые позиции</th></tr>
            </thead>
            <tbody>
              {deltas.map((delta) => {
                const counts = (delta.counts ?? {}) as Record<string, unknown>;
                const unresolved = Array.isArray(delta.unresolved_items)
                  ? (delta.unresolved_items as Array<Record<string, unknown>>)
                  : [];
                return (
                  <tr key={`${String(delta.delta_id)}:${String(delta.version)}`}>
                    <td>
                      {humanizeAuditDeltaKind(
                        typeof delta.kind === "string" ? delta.kind : "unknown",
                      )}
                    </td>
                    <td>{Object.entries(counts).map(([key, count]) => `${humanizeStatus(key)}: ${String(count)}`).join(", ")}</td>
                    <td>{unresolved.map((item) => String(item.item_key)).join(", ") || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>Запросы на исправление</h2>
        {requests.length ? (
          <div className="table-wrap"><table><thead><tr><th>Действие</th><th>Объект</th><th>Состояние</th><th>Основание и последствия</th></tr></thead><tbody>
            {requests.map((item) => <tr key={`${String(item.action_request_id)}:${String(item.version)}`}><td>{String(item.action_code)}</td><td>{String(item.affected_object_ref)}</td><td>{humanizeStatus(String(item.state))}</td><td><GapList gaps={[...((item.evidence_refs as string[] | undefined) ?? []), ...((item.blocking_impacts as string[] | undefined) ?? [])]} /></td></tr>)}
          </tbody></table></div>
        ) : <InfoNotice>В этот отчёт не включены запросы на исправление.</InfoNotice>}
      </section>
      {gaps.length ? <GapList gaps={gaps} /> : null}
    </>
  );
}

function AuditExpectedActualPreflightBody({
  value,
  workspaceId,
}: {
  value: AuditExpectedActualPreflight;
  workspaceId: string;
}) {
  const counts = value.counts;
  const items = value.items as unknown as AuditPreflightItem[];
  return (
    <>
      <InfoNotice>
        Здесь показан состав подготовленного комплекта относительно версии
        матрицы требований. Наличие кандидата или финализированного документа не
        означает, что его содержание, подписи и приложения прошли независимый
        аудит.
      </InfoNotice>
      <section
        className="metrics"
        aria-label="Состояние предварительной сверки"
      >
        <Metric label="Требований" value={items.length} />
        <Metric label="Отсутствует" value={counts.missing ?? 0} />
        <Metric label="Подготовлено" value={counts.generated_candidate ?? 0} />
        <Metric label="Ожидает аудита" value={counts.awaiting_audit ?? 0} />
      </section>
      <section className="panel">
        <div className="entity-heading">
          <h2>Требования и фактический состав</h2>
          <div className="inline-actions">
            <StatusPill tone="warning">
              {value.status === "not_started"
                ? "Требования ещё не сформированы"
                : "Предварительный результат"}
            </StatusPill>
            <a
              className="button-link secondary"
              href={`/api/v1/workspaces/${workspaceId}/audit/expected-actual-preflight.csv`}
            >
              Скачать таблицу
            </a>
          </div>
        </div>
        {items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Работа / документ</th>
                  <th>Состояние</th>
                  <th>Комплект</th>
                  <th>Основания, последствия и необходимое действие</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.item_key}>
                    <td>
                      <strong>
                        {humanizeDocumentRole(item.document_type)}
                      </strong>
                      <small className="mono">{item.work_package_id}</small>
                    </td>
                    <td>
                      <StatusPill
                        tone={
                          item.preflight_state === "missing"
                            ? "warning"
                            : "default"
                        }
                      >
                        {humanizeAuditPreflightState(item.preflight_state)}
                      </StatusPill>
                    </td>
                    <td>
                      <small>Позиций: {item.membership_count}</small>
                      {item.membership_states.length ? (
                        <small>
                          {item.membership_states
                            .map(humanizeStatus)
                            .join(", ")}
                        </small>
                      ) : (
                        <small>Позиция не сформирована</small>
                      )}
                    </td>
                    <td>
                      <GapList gaps={[...item.evidence_refs, ...item.gaps]} />
                      <p>
                        Последствие:{" "}
                        {humanizeAuditConsequence(item.practical_consequence)}.
                      </p>
                      <p>
                        Действие:{" "}
                        {humanizeAuditCorrection(item.required_correction)}.
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <InfoNotice>
            Матрица требований ещё не содержит позиций для предварительной
            сверки.
          </InfoNotice>
        )}
      </section>
      {value.gaps.length ? (
        <section className="panel">
          <h2>Что препятствует независимому аудиту</h2>
          <GapList gaps={value.gaps} />
        </section>
      ) : null}
    </>
  );
}

function RestorationRecoveryPlanPage() {
  const { workspaceId = "" } = useParams();
  const queryClient = useQueryClient();
  const plan = useQuery({
    queryKey: ["restoration-recovery-plan", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/restoration/recovery-plan",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
  });
  const capture = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/restoration/recovery-plans",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["restoration-recovery-plan", workspaceId],
      });
    },
  });
  return (
    <Page
      title="План восстановления комплекта"
      lead="Очередность действий по требованиям и имеющимся доказательствам без подстановки отсутствующих фактов."
    >
      <QueryState query={plan}>
        {(value) => (
          <RestorationRecoveryPlanBody
            value={value}
            workspaceId={workspaceId}
            capture={() => capture.mutate()}
            capturePending={capture.isPending}
            captureError={capture.error}
          />
        )}
      </QueryState>
    </Page>
  );
}

function RestorationRecoveryPlanBody({
  value,
  workspaceId,
  capture,
  capturePending,
  captureError,
}: {
  value: RestorationRecoveryPlan;
  workspaceId: string;
  capture: () => void;
  capturePending: boolean;
  captureError: unknown;
}) {
  const recoverable = value.recoverable_actions as unknown as Array<
    Record<string, unknown>
  >;
  const blocked = value.blocked_actions as unknown as Array<
    Record<string, unknown>
  >;
  return (
    <>
      <InfoNotice>
        План не подтверждает выполнение работ и не создаёт даты, подписи,
        измерения или результаты испытаний. Для отсутствующих исходных данных
        указано, что именно необходимо получить.
      </InfoNotice>
      <section className="metrics" aria-label="Состояние восстановления">
        <Metric label="Можно продолжить" value={recoverable.length} />
        <Metric label="Требуют исходных данных" value={blocked.length} />
      </section>
      <a
        className="button-link secondary"
        href={`/api/v1/workspaces/${workspaceId}/restoration/recovery-plan.csv`}
      >
        Скачать редактируемый план восстановления
      </a>
      <button
        type="button"
        className="button-link secondary"
        onClick={capture}
        disabled={capturePending}
      >
        {capturePending
          ? "Фиксация плана…"
          : "Зафиксировать план восстановления"}
      </button>
      {value.snapshot ? (
        <InfoNotice>
          Зафиксирована версия {String(value.snapshot.version)} плана.
          {value.snapshot_is_current
            ? " Она соответствует текущим основаниям."
            : " Она относится к прежнему состоянию оснований; текущий план можно зафиксировать новой версией."}{" "}
          Фиксация не изменяет исходные документы или факты.
        </InfoNotice>
      ) : (
        <InfoNotice>
          Текущий план ещё не зафиксирован. Фиксация создаёт воспроизводимую
          версию оценки без создания недостающих документов.
        </InfoNotice>
      )}
      {captureError ? <ErrorNotice error={captureError} /> : null}
      <RecoveryActionTable
        title="Действия с доступными основаниями"
        items={recoverable}
        workspaceId={workspaceId}
      />
      <RecoveryActionTable
        title="Блокирующие отсутствующие сведения"
        items={blocked}
        workspaceId={workspaceId}
      />
      {value.global_blockers.length ? (
        <section className="panel">
          <h2>Общие ограничения</h2>
          <GapList gaps={value.global_blockers} />
        </section>
      ) : null}
    </>
  );
}

function RecoveryActionTable({
  title,
  items,
  workspaceId,
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  workspaceId: string;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Документ</th>
                <th>Действие</th>
                <th>Необходимые данные</th>
                <th>Основания</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={String(item.item_key)}>
                  <td>
                    <strong>
                      {humanizeDocumentRole(String(item.document_type))}
                    </strong>
                    <small className="mono">
                      {String(item.work_package_id)}
                    </small>
                  </td>
                  <td>{humanizeRecoveryAction(String(item.action))}</td>
                  <td>
                    {String(item.required_input)}
                    {Array.isArray(item.generated_candidate_ids) &&
                    item.generated_candidate_ids.length > 0 ? (
                      <small>
                        <Link
                          to={workspaceRouteFromSlug(
                            "support",
                            workspaceId,
                            "/id-production",
                          )}
                        >
                          Открыть подготовленный кандидат в комплекте ИД
                        </Link>
                      </small>
                    ) : null}
                  </td>
                  <td>
                    <GapList
                      gaps={[
                        ...((item.evidence_refs as string[] | undefined) ?? []),
                        ...((item.blocker_codes as string[] | undefined) ?? []),
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <InfoNotice>Позиции этого типа не зарегистрированы.</InfoNotice>
      )}
    </section>
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
  const fieldRows = mergeFieldResolutionRows(fields);
  const supportProcess = value.support_process;
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
        {!value.package && !supportProcess && (
          <InfoNotice>
            Перед формированием комплекта нужно настроить контур сопровождения
            для этого ОКС с полномочием специалиста. Без него пакет не будет
            иметь закреплённого объёма работ, политики и версии правил.
          </InfoNotice>
        )}
        {!value.package && supportProcess &&
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
            <a
              className="button-link secondary"
              href={`/api/v1/workspaces/${workspaceId}/support/id-packages/export`}
            >
              Скачать редактируемый комплект
            </a>
            <p>
              Реестр находится первым файлом архива. Подготовленные документы
              сохранены как кандидаты, а отсутствующие и заблокированные позиции
              перечислены отдельным графиком.
            </p>
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
            <h2>Поля, доказательства и недостающие входные данные</h2>
            {fieldRows.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Поле</th>
                      <th>Значение</th>
                      <th>Состояние</th>
                      <th>Источники</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fieldRows.map(({ field, locatorIds }) => (
                      <tr
                        key={`${String(field.generation_run_id)}:${String(field.field_key)}:${String(field.state)}`}
                      >
                        <td>{humanizeFieldKey(String(field.field_key))}</td>
                        <td>
                          {displayValue(field.display_value, "Не установлено")}
                        </td>
                        <td>
                          <StatusPill
                            tone={
                              String(field.state) === "confirmed"
                                ? "default"
                                : "warning"
                            }
                          >
                            {humanizeStatus(String(field.state))}
                          </StatusPill>
                        </td>
                        <td>
                          {locatorIds.length ? (
                            locatorIds.map((locatorId, index) => (
                              <span key={locatorId}>
                                {index > 0 ? ", " : ""}
                                <Link
                                  to={workspaceRouteFromSlug(
                                    modeSlug,
                                    workspaceId,
                                    `/evidence/locators/${locatorId}`,
                                  )}
                                >
                                  открыть источник
                                </Link>
                              </span>
                            ))
                          ) : (
                            <small>Источник ещё не установлен</small>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
              {value.matrix_version_id ? (
                <Link
                  className="button-link"
                  to={primaryModeOutputRoute(normalized, workspaceId)}
                >
                  {normalized === "Tender"
                    ? "Открыть анализ проекта"
                    : normalized === "Support"
                      ? "Открыть комплект ИД"
                      : normalized === "Audit"
                        ? "Открыть предварительную сверку"
                        : "Открыть план восстановления"}
                </Link>
              ) : (
                <Link
                  className="button-link"
                  to={workspaceRoute(normalized, workspaceId, "/documents")}
                >
                  Добавить исходные документы
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

function PilotResultPage() {
  const { workspaceId = "", mode: modeSlug } = useParams();
  const mode = modeFromSlug(modeSlug);
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: ["pilot-result", workspaceId, mode],
    enabled: Boolean(mode),
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/modes/{mode}/result",
        {
          params: {
            path: { workspace_id: workspaceId, mode: mode ?? "Tender" },
          },
        },
      );
      return requireData(data, error);
    },
  });
  const formResult = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/modes/{mode}/result",
        {
          params: {
            path: { workspace_id: workspaceId, mode: mode ?? "Tender" },
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["pilot-result", workspaceId, mode],
      });
    },
  });
  const review = useMutation({
    mutationFn: async (payload: {
      itemId: string;
      action:
        "accepted" | "corrected" | "excluded" | "status_changed" | "commented";
      resolvedFields: Record<string, unknown> | null;
      comment: string;
    }) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/modes/{mode}/result/items/{item_id}/reviews",
        {
          params: {
            path: {
              workspace_id: workspaceId,
              mode: mode ?? "Tender",
              item_id: payload.itemId,
            },
          },
          body: {
            action: payload.action,
            resolved_fields: payload.resolvedFields,
            comment: payload.comment,
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["pilot-result", workspaceId, mode],
      });
    },
  });
  const createExport = useMutation({
    mutationFn: async (payload: {
      exportKind:
        | "disagreement_protocol"
        | "contract_changes"
        | "requirement_matrix"
        | "id_package"
        | "register"
        | "audit_report"
        | "recovery_plan"
        | "recovered_drafts"
        | "workspace_results";
      outputFormat: "docx" | "pdf" | "zip";
    }) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/modes/{mode}/exports",
        {
          params: {
            path: { workspace_id: workspaceId, mode: mode ?? "Tender" },
          },
          body: {
            export_kind: payload.exportKind,
            output_format: payload.outputFormat,
          },
        },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["pilot-result", workspaceId, mode],
      });
    },
  });
  if (!mode) return <Navigate to="/modes" replace />;
  const definition = MODE_DEFINITIONS[mode];
  return (
    <Page
      title={`Результат: ${definition.title}`}
      lead="Проверьте выводы, откройте исходные фрагменты и сформируйте рабочие документы."
    >
      {result.isError && !formResult.isSuccess ? (
        <section className="panel result-empty">
          <h2>Сформируйте первый результат</h2>
          <p>
            Комплекс использует общую модель объекта и не подставляет
            отсутствующие факты. Нерешённые вопросы останутся видимыми.
          </p>
          <button
            type="button"
            onClick={() => formResult.mutate()}
            disabled={formResult.isPending}
          >
            Сформировать результат
          </button>
          {formResult.isError && <ErrorNotice error={formResult.error} />}
        </section>
      ) : (
        <QueryState query={result}>
          {(value) => (
            <PilotResultBody
              value={value}
              workspaceId={workspaceId}
              mode={mode}
              {...(modeSlug === undefined ? {} : { modeSlug })}
              review={(payload) => review.mutate(payload)}
              reviewPending={review.isPending}
              createExport={(payload) => createExport.mutate(payload)}
              exportPending={createExport.isPending}
              commandError={review.error ?? createExport.error}
            />
          )}
        </QueryState>
      )}
    </Page>
  );
}

function PilotResultBody({
  value,
  workspaceId,
  mode,
  modeSlug,
  review,
  reviewPending,
  createExport,
  exportPending,
  commandError,
}: {
  value: PilotResult;
  workspaceId: string;
  mode: ModeName;
  modeSlug?: string;
  review: (payload: {
    itemId: string;
    action:
      "accepted" | "corrected" | "excluded" | "status_changed" | "commented";
    resolvedFields: Record<string, unknown> | null;
    comment: string;
  }) => void;
  reviewPending: boolean;
  createExport: (payload: {
    exportKind:
      | "disagreement_protocol"
      | "contract_changes"
      | "requirement_matrix"
      | "id_package"
      | "register"
      | "audit_report"
      | "recovery_plan"
      | "recovered_drafts"
      | "workspace_results";
    outputFormat: "docx" | "pdf" | "zip";
  }) => void;
  exportPending: boolean;
  commandError: unknown;
}) {
  const [statusFilter, setStatusFilter] = useState("all");
  const [resultSearch, setResultSearch] = useState("");
  const filteredItems = value.items.filter((item) => {
    const status = pilotItemStatus(item);
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "open"
        ? !["accepted", "excluded", "conforms"].includes(status)
        : status === statusFilter);
    const haystack = `${displayValue(item.title)} ${displayValue(
      item.effective_description ?? item.description,
    )}`.toLocaleLowerCase("ru-RU");
    return (
      matchesStatus &&
      haystack.includes(resultSearch.trim().toLocaleLowerCase("ru-RU"))
    );
  });
  const tenderScopeSchedule = Array.isArray(value.tender_scope_schedule)
    ? (value.tender_scope_schedule as Record<string, unknown>[])
    : [];
  return (
    <>
      <section className="metrics" aria-label="Сводка результата">
        <Metric label="Выводов" value={Number(value.summary.items ?? 0)} />
        <Metric
          label="Требуют решения"
          value={Number(value.summary.open_questions ?? 0)}
        />
        <Metric label="Рассмотрено" value={value.reviewed_item_count} />
        <Metric
          label="Наблюдений работ"
          value={Number(
            value.summary.candidate_work_observation_groups ??
              value.summary.work_packages ??
              0,
          )}
        />
      </section>
      <InfoNotice>{value.normative_notice}.</InfoNotice>
      <section className="panel toolbar result-toolbar">
        <label>
          Найти в результатах
          <input
            type="search"
            value={resultSearch}
            onChange={(event) => setResultSearch(event.target.value)}
            placeholder="Работа, материал или замечание"
          />
        </label>
        <label>
          Состояние
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="all">Все</option>
            <option value="open">Требуют решения</option>
            <option value="accepted">Приняты</option>
            <option value="excluded">Исключены</option>
            <option value="conflict">Расхождения</option>
            <option value="missing">Отсутствуют</option>
          </select>
        </label>
      </section>
      {mode === "Tender" && tenderScopeSchedule.length > 0 && (
        <section className="panel">
          <div className="entity-heading">
            <div>
              <h2>Состав работ и ресурсов из модели объекта</h2>
              <p>
                Наблюдения сохраняют область и источники. Одинаковые названия из
                разных областей не объединяются в общий объём.
              </p>
            </div>
            <StatusPill tone="warning">Кандидаты</StatusPill>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Работа и область</th>
                  <th>Количество по источнику</th>
                  <th>Материалы</th>
                  <th>Источники и ограничения</th>
                </tr>
              </thead>
              <tbody>
                {tenderScopeSchedule.map((row) => {
                  const quantities = Array.isArray(row.quantities)
                    ? (row.quantities as Record<string, unknown>[])
                    : [];
                  const materials = Array.isArray(row.materials)
                    ? (row.materials as Record<string, unknown>[])
                    : [];
                  const locators = Array.isArray(row.source_locator_ids)
                    ? row.source_locator_ids.map(String)
                    : [];
                  const uncertainties = Array.isArray(row.uncertainties)
                    ? row.uncertainties.map(String)
                    : [];
                  return (
                    <tr key={String(row.work_package_id)}>
                      <td>
                        <strong>{displayValue(row.work_name)}</strong>
                        <br />
                        <span>
                          {displayValue(row.scope, "Область не указана")}
                        </span>
                      </td>
                      <td>
                        {quantities.length
                          ? quantities
                              .map((value) =>
                                [value.raw_value, value.raw_unit]
                                  .filter(
                                    (item) =>
                                      item !== null &&
                                      item !== undefined &&
                                      item !== "",
                                  )
                                  .map(String)
                                  .join(" "),
                              )
                              .join("; ")
                          : "Не указано в извлечённом наблюдении"}
                      </td>
                      <td>
                        {materials.length
                          ? materials
                              .map((value) => {
                                const amount = [
                                  value.raw_quantity,
                                  value.raw_unit,
                                ]
                                  .filter(
                                    (item) =>
                                      item !== null &&
                                      item !== undefined &&
                                      item !== "",
                                  )
                                  .map(String)
                                  .join(" ");
                                return `${displayValue(value.raw_name, "Материал не указан")}${amount ? ` — ${amount}` : ""}`;
                              })
                              .join("; ")
                          : "Не указаны в извлечённом наблюдении"}
                      </td>
                      <td>
                        {locators.map((locator, index) => (
                          <Link
                            key={locator}
                            to={workspaceRouteFromSlug(
                              modeSlug,
                              workspaceId,
                              `/evidence/locators/${locator}`,
                            )}
                          >
                            Исходный фрагмент {index + 1}
                          </Link>
                        ))}
                        {uncertainties.length > 0 && (
                          <GapList gaps={uncertainties.map(humanizeGap)} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="panel">
        <div className="entity-heading">
          <div>
            <h2>Выводы и действия</h2>
            <p>
              Каждый существенный вывод можно сопоставить с исходным фрагментом
              и отдельно рассмотреть.
            </p>
          </div>
          <StatusPill tone="warning">{humanizeStatus(value.status)}</StatusPill>
        </div>
        <div className="pilot-result-list">
          {filteredItems.map((item) => (
            <PilotResultItem
              key={String(item.item_id)}
              item={item}
              workspaceId={workspaceId}
              {...(modeSlug === undefined ? {} : { modeSlug })}
              onReview={review}
              pending={reviewPending}
            />
          ))}
          {filteredItems.length === 0 && (
            <p className="empty-state">
              По выбранному фильтру результатов нет.
            </p>
          )}
        </div>
      </section>
      <section className="panel">
        <h2>Сформировать документы</h2>
        <p>
          Экспорт содержит название объекта, версию результата, использованные
          источники и нерешённые вопросы.
        </p>
        <div className="export-grid">
          {value.available_exports.map((kind) => (
            <article className="export-card" key={kind}>
              <strong>{humanizeExportKind(kind)}</strong>
              <div className="candidate-actions">
                <button
                  className="ghost"
                  type="button"
                  disabled={exportPending}
                  onClick={() =>
                    createExport({
                      exportKind: kind as Parameters<
                        typeof createExport
                      >[0]["exportKind"],
                      outputFormat: "docx",
                    })
                  }
                >
                  Подготовить DOCX
                </button>
                <button
                  className="ghost"
                  type="button"
                  disabled={exportPending}
                  onClick={() =>
                    createExport({
                      exportKind: kind as Parameters<
                        typeof createExport
                      >[0]["exportKind"],
                      outputFormat: "pdf",
                    })
                  }
                >
                  Подготовить PDF
                </button>
                {["id_package", "recovered_drafts"].includes(kind) && (
                  <button
                    className="ghost"
                    type="button"
                    disabled={exportPending}
                    onClick={() =>
                      createExport({
                        exportKind: kind as Parameters<
                          typeof createExport
                        >[0]["exportKind"],
                        outputFormat: "zip",
                      })
                    }
                  >
                    Подготовить архив
                  </button>
                )}
              </div>
            </article>
          ))}
          <article className="export-card">
            <strong>Архив результатов объекта</strong>
            <p>Доступен после формирования результатов всех четырёх режимов.</p>
            <button
              className="ghost"
              type="button"
              disabled={exportPending}
              onClick={() =>
                createExport({
                  exportKind: "workspace_results",
                  outputFormat: "zip",
                })
              }
            >
              Подготовить общий архив
            </button>
          </article>
        </div>
        {commandError !== null && commandError !== undefined ? (
          <ErrorNotice error={commandError} />
        ) : null}
        {(value.exports ?? []).length > 0 && (
          <div className="download-list">
            <h3>Готовые файлы</h3>
            {(value.exports ?? []).map((item) => (
              <a
                className="button-link secondary"
                key={`${String(item.export_id)}:${String(item.version)}`}
                href={`/api/v1/workspaces/${workspaceId}/pilot-exports/${String(item.export_id)}/content`}
              >
                Скачать {humanizeExportKind(String(item.export_kind))} (
                {String(item.output_format).toUpperCase()})
              </a>
            ))}
          </div>
        )}
      </section>
      {mode === "Support" && (
        <section className="panel">
          <h2>Исполнительная документация</h2>
          <p>
            Финализированный АОСР и версии реестра сохраняются в действующем
            комплекте исполнительной документации.
          </p>
          <Link
            className="button-link"
            to={workspaceRoute(mode, workspaceId, "/support-id")}
          >
            Открыть комплект ИД
          </Link>
        </section>
      )}
    </>
  );
}

function PilotResultItem({
  item,
  workspaceId,
  modeSlug,
  onReview,
  pending,
}: {
  item: Record<string, unknown>;
  workspaceId: string;
  modeSlug?: string;
  onReview: (payload: {
    itemId: string;
    action:
      "accepted" | "corrected" | "excluded" | "status_changed" | "commented";
    resolvedFields: Record<string, unknown> | null;
    comment: string;
  }) => void;
  pending: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [commenting, setCommenting] = useState(false);
  const [changingStatus, setChangingStatus] = useState(false);
  const [statusValue, setStatusValue] = useState("requires_clarification");
  const [description, setDescription] = useState(
    displayValue(item.effective_description ?? item.description),
  );
  const [comment, setComment] = useState("");
  const locators = Array.isArray(item.source_locator_ids)
    ? item.source_locator_ids.map(String)
    : [];
  const identity = String(item.item_id);
  const submit = (
    action:
      "accepted" | "corrected" | "excluded" | "status_changed" | "commented",
  ) => {
    onReview({
      itemId: identity,
      action,
      resolvedFields:
        action === "corrected"
          ? { description }
          : action === "status_changed"
            ? {
                status: statusValue,
                resolution_status:
                  statusValue === "conforms" ? "resolved" : "open",
              }
            : null,
      comment:
        comment ||
        (action === "accepted"
          ? "Вывод принят после проверки источника"
          : "Результат рассмотрен пользователем"),
    });
    setEditing(false);
    setCommenting(false);
    setChangingStatus(false);
  };
  return (
    <article className="pilot-result-item">
      <div className="entity-heading">
        <div>
          <h3>{displayValue(item.title, "Вывод")}</h3>
          <StatusPill
            tone={
              ["conforms", "accepted"].includes(pilotItemStatus(item))
                ? "default"
                : "warning"
            }
          >
            {humanizeStatus(pilotItemStatus(item))}
          </StatusPill>
        </div>
        <div className="candidate-actions">
          <button
            type="button"
            className="ghost"
            disabled={pending}
            onClick={() => submit("accepted")}
          >
            Принять
          </button>
          <button
            type="button"
            className="ghost"
            disabled={pending}
            onClick={() => setEditing(true)}
          >
            Исправить
          </button>
          <button
            type="button"
            className="ghost"
            disabled={pending}
            onClick={() => submit("excluded")}
          >
            Исключить
          </button>
          <button
            type="button"
            className="ghost"
            disabled={pending}
            onClick={() => setCommenting(true)}
          >
            Комментарий
          </button>
          <button
            type="button"
            className="ghost"
            disabled={pending}
            onClick={() => setChangingStatus(true)}
          >
            Изменить статус
          </button>
        </div>
      </div>
      <p>{displayValue(item.effective_description ?? item.description)}</p>
      <dl className="result-details">
        <div>
          <dt>Последствия</dt>
          <dd>{displayValue(item.consequence)}</dd>
        </div>
        <div>
          <dt>Рекомендуемое действие</dt>
          <dd>{displayValue(item.recommended_action)}</dd>
        </div>
      </dl>
      {locators.length ? (
        <div className="source-links">
          <strong>Источник:</strong>
          {locators.map((locator, index) => (
            <Link
              key={locator}
              to={workspaceRouteFromSlug(
                modeSlug,
                workspaceId,
                `/evidence/locators/${locator}`,
              )}
            >
              Исходный фрагмент {index + 1}
            </Link>
          ))}
        </div>
      ) : (
        <p className="muted-copy">
          Точный исходный фрагмент для этого вывода требует уточнения.
        </p>
      )}
      {item.review ? (
        <small>
          Последнее решение:{" "}
          {humanizeStatus(
            String((item.review as Record<string, unknown>).action),
          )}{" "}
          · {String((item.review as Record<string, unknown>).comment)}
        </small>
      ) : null}
      {editing && (
        <div className="candidate-edit">
          <label>
            Исправленная формулировка
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          <label>
            Причина или комментарий
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={
              pending ||
              description.trim().length < 3 ||
              comment.trim().length < 3
            }
            onClick={() => submit("corrected")}
          >
            Сохранить новую версию решения
          </button>
        </div>
      )}
      {commenting && (
        <div className="candidate-edit">
          <label>
            Комментарий
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={pending || comment.trim().length < 3}
            onClick={() => submit("commented")}
          >
            Сохранить комментарий
          </button>
        </div>
      )}
      {changingStatus && (
        <div className="candidate-edit">
          <label>
            Новое состояние
            <select
              value={statusValue}
              onChange={(event) => setStatusValue(event.target.value)}
            >
              <option value="conforms">Соответствует</option>
              <option value="requires_clarification">Требует уточнения</option>
              <option value="conflict">Противоречит другому источнику</option>
              <option value="missing">Отсутствует</option>
              <option value="cannot_prepare">
                Невозможно проверить по имеющимся данным
              </option>
            </select>
          </label>
          <label>
            Основание изменения
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={pending || comment.trim().length < 3}
            onClick={() => submit("status_changed")}
          >
            Сохранить состояние
          </button>
        </div>
      )}
    </article>
  );
}

function ProjectUnderstandingPage() {
  const { workspaceId = "", mode } = useParams();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [section, setSection] = useState(
    searchParams.get("section") ?? "general",
  );
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
    refetchInterval: 5_000,
  });
  const start = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/project-understanding/runs",
        { params: { path: { workspace_id: workspaceId } } },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["project-understanding", workspaceId],
        }),
        queryClient.invalidateQueries({ queryKey: ["jobs", workspaceId] }),
      ]);
    },
  });
  const review = useMutation({
    mutationFn: async (payload: {
      candidate_kind: "project_field" | "work_type" | "quantity" | "material";
      candidate_id: string;
      candidate_version: number;
      action: "confirmed" | "rejected" | "corrected";
      resolved_value: string | number | boolean | null;
      reason: string;
    }) => {
      const { data, error } = await api.POST(
        "/api/v1/workspaces/{workspace_id}/project-understanding/reviews",
        { params: { path: { workspace_id: workspaceId } }, body: payload },
      );
      return requireData(data, error);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["project-understanding", workspaceId],
      });
    },
  });
  const sections = [
    ["general", "Общие сведения"],
    ["structure", "Структура объекта"],
    ["works", "Виды и объёмы работ"],
    ["materials", "Материалы и изделия"],
    ["packages", "Пакеты работ"],
    ["matrix", "Матрица требований"],
    ["gaps", "Расхождения и пробелы"],
  ] as const;
  return (
    <Page
      title="Модель объекта"
      lead="Структура ОКС, работы, объёмы, материалы и требования, сформированные из загруженных документов."
    >
      <div className="model-actions">
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending}
        >
          Сформировать модель объекта
        </button>
        <Link
          className="button-link secondary"
          to={workspaceRouteFromSlug(mode, workspaceId, "/documents")}
        >
          Добавить исходные документы
        </Link>
      </div>
      {start.isPending && (
        <InfoNotice>
          Формирование модели поставлено в очередь обработки…
        </InfoNotice>
      )}
      {start.isError && <ErrorNotice error={start.error} />}
      {review.isError && <ErrorNotice error={review.error} />}
      <nav className="model-tabs" aria-label="Разделы модели объекта">
        {sections.map(([key, label]) => (
          <button
            type="button"
            className={section === key ? "active" : "ghost"}
            key={key}
            onClick={() => {
              setSection(key);
              setSearchParams({ section: key }, { replace: true });
            }}
          >
            {label}
          </button>
        ))}
      </nav>
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
          const candidates = (value.candidates ?? {}) as Record<
            string,
            Record<string, unknown>[]
          >;
          const structureNodes = (value.structure_nodes ?? []) as Record<
            string,
            unknown
          >[];
          const structureRelationships = (value.structure_relationships ??
            []) as Record<string, unknown>[];
          const structureDossiers = (value.structure_dossiers ?? []) as Record<
            string,
            unknown
          >[];
          const structureComponents = (value.structure_components ??
            []) as Record<string, unknown>[];
          const structureIdentityCandidates =
            (value.structure_identity_candidates ?? []) as Record<
              string,
              unknown
            >[];
          const decisions = (value.review_decisions ?? []) as Record<
            string,
            unknown
          >[];
          const matrixValue = (value.matrix.matrix ?? {}) as Record<
            string,
            unknown
          >;
          const matrixRows = Array.isArray(matrixValue.rows)
            ? (matrixValue.rows as Record<string, unknown>[])
            : [];
          const materialization = value.materialization as Record<
            string,
            unknown
          >;
          const materializationState =
            typeof materialization.state === "string"
              ? materialization.state
              : "not_requested";
          const semanticCoverage = Array.isArray(value.semantic_coverage)
            ? (value.semantic_coverage as Record<string, unknown>[])
            : [];
          const tenderInputAssessment = Array.isArray(
            (value.intake_summary as Record<string, unknown> | undefined)
              ?.tender_input_assessment,
          )
            ? ((value.intake_summary as Record<string, unknown>)
                .tender_input_assessment as Record<string, unknown>[])
            : [];
          const projectFieldCandidates = candidates.project_fields ?? [];
          const workCandidates = candidates.work_types ?? [];
          const quantityCandidates = candidates.quantities ?? [];
          const materialCandidates = candidates.materials ?? [];
          const materializationMessages: Record<string, string> = {
            not_requested:
              "Модель объекта ещё не запускалась. Загруженные документы сохранены отдельно от модели.",
            queued:
              "Формирование модели ожидает выполнения зависимых задач обработки.",
            running:
              "Формирование модели объекта выполняется; промежуточные сведения сохраняются с источниками.",
            blocked:
              "Формирование модели заблокировано внутренней зависимостью обработки. Это не означает отсутствие замечаний или сведений в документах.",
            partial:
              "Модель сформирована частично: используйте сведения и источники с учётом указанных пробелов.",
          };
          return (
            <>
              <div className="metrics">
                <Metric
                  label="Сведений-кандидатов"
                  value={projectFieldCandidates.length}
                />
                <Metric
                  label="Структур-кандидатов"
                  value={structureNodes.length}
                />
                <Metric
                  label="Связей-кандидатов"
                  value={structureRelationships.length}
                />
                <Metric
                  label="Междокументных групп-кандидатов"
                  value={structureIdentityCandidates.length}
                />
                <Metric
                  label="Работ-кандидатов"
                  value={workCandidates.length}
                />
                <Metric
                  label="Количеств-кандидатов"
                  value={quantityCandidates.length}
                />
                <Metric
                  label="Материалов-кандидатов"
                  value={materialCandidates.length}
                />
                <Metric
                  label="Классифицировано страниц"
                  value={value.page_roles.length}
                />
              </div>
              {materializationState !== "complete" && (
                <InfoNotice>
                  {materializationMessages[materializationState] ??
                    "Состояние формирования модели требует проверки."}
                  {typeof materialization.failure_code === "string" &&
                    ` Причина: ${materialization.failure_code}.`}
                </InfoNotice>
              )}
              {semanticCoverage.length > 0 && (
                <InfoNotice>
                  Семантическая обработка сохраняет результаты по фрагментам:{" "}
                  {semanticCoverage
                    .map((item) => {
                      const accepted = Number(
                        item.accepted_fragment_count ?? 0,
                      );
                      const expected = Number(
                        item.expected_fragment_count ?? 0,
                      );
                      const failed = Number(item.failed_fragment_count ?? 0);
                      const unresolved = Number(
                        item.unresolved_failed_fragment_count ?? 0,
                      );
                      const recovered = Number(
                        item.recovered_failed_fragment_count ?? 0,
                      );
                      const profile = displayValue(
                        item.profile_version,
                        "профиль",
                      );
                      const documentName = displayValue(
                        item.safe_display_name,
                        "документ",
                      );
                      const pages = Number(item.page_count ?? 0);
                      const pageLabel =
                        pages > 0 ? `, ${pages.toString()} стр.` : "";
                      const unresolvedLabel =
                        unresolved > 0
                          ? `, требуется восстановление: ${unresolved.toString()} фрагм.`
                          : "";
                      const recoveredLabel =
                        recovered > 0
                          ? `, восстановленные исторические попытки: ${recovered.toString()} фрагм.`
                          : "";
                      const legacyFailureLabel =
                        failed > 0 && unresolved === 0 && recovered === 0
                          ? `, неуспешные попытки: ${failed.toString()} фрагм.`
                          : "";
                      return `${documentName}${pageLabel}: ${accepted.toString()}/${expected.toString()} фрагментов${unresolvedLabel}${recoveredLabel}${legacyFailureLabel} (${profile})`;
                    })
                    .join("; ")}
                  . Это покрытие извлечения-кандидата, а не подтверждённые
                  факты.
                </InfoNotice>
              )}
              {section === "general" && tenderInputAssessment.length > 0 && (
                <section className="panel">
                  <h2>Исходные данные для Tender-анализа</h2>
                  <p>
                    Оценка описывает доступность исходных документов для
                    отдельных проверок. Отсутствие договора не отменяет анализ
                    проектных решений, но ограничивает договорные выводы.
                  </p>
                  <TenderInputAssessmentTable
                    items={tenderInputAssessment}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                  />
                </section>
              )}
              {section === "general" && (
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
                    <h2>Сведения, требующие решения</h2>
                    <CandidateReviewTable
                      kind="project_field"
                      candidates={candidates.project_fields ?? []}
                      decisions={decisions}
                      workspaceId={workspaceId}
                      modeSlug={mode}
                      onReview={(payload) => review.mutate(payload)}
                      pending={review.isPending}
                    />
                  </section>
                </div>
              )}
              {section === "structure" && (
                <section className="panel">
                  <h2>Структура объекта</h2>
                  <p>
                    Части объекта, зоны, уровни и фронты работ отображаются
                    только при наличии точного исходного фрагмента.
                    Неразрешённые пространственные сведения остаются пробелом.
                  </p>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-structure-identity-candidates.csv`}
                  >
                    Скачать ведомость междокументных групп-кандидатов
                  </a>
                  <StructureCandidateList
                    nodes={structureNodes}
                    relationships={structureRelationships}
                    dossiers={structureDossiers}
                    components={structureComponents}
                    identityCandidates={structureIdentityCandidates}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                  />
                  <h3>Классифицированные страницы</h3>
                  <EvidenceObject value={{ pages: value.page_roles }} />
                </section>
              )}
              {section === "works" && (
                <section className="panel">
                  <h2>Виды и объёмы работ</h2>
                  <CandidateReviewTable
                    kind="work_type"
                    candidates={candidates.work_types ?? []}
                    decisions={decisions}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                    onReview={(payload) => review.mutate(payload)}
                    pending={review.isPending}
                  />
                  <CandidateReviewTable
                    kind="quantity"
                    candidates={candidates.quantities ?? []}
                    decisions={decisions}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                    onReview={(payload) => review.mutate(payload)}
                    pending={review.isPending}
                  />
                </section>
              )}
              {section === "materials" && (
                <section className="panel">
                  <h2>Материалы и изделия</h2>
                  <CandidateReviewTable
                    kind="material"
                    candidates={candidates.materials ?? []}
                    decisions={decisions}
                    workspaceId={workspaceId}
                    modeSlug={mode}
                    onReview={(payload) => review.mutate(payload)}
                    pending={review.isPending}
                  />
                </section>
              )}
              {section === "packages" && (
                <section className="panel">
                  <h2>Исходные наблюдения по работам</h2>
                  <p>
                    Повторные наблюдения объединяются только в пределах одного
                    источника и явно указанной области. Одинаковые названия в
                    разных областях не суммируются и остаются отдельными до
                    инженерской сверки.
                  </p>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-scope-schedule.csv`}
                  >
                    Скачать редактируемую ведомость работ и ресурсов
                  </a>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-document-coverage.csv`}
                  >
                    Скачать покрытие документов
                  </a>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-facility-work-observations.csv`}
                  >
                    Скачать связь наблюдений работ с группами объектов
                  </a>
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
                    <p className="empty-state">
                      Наблюдения по работам ещё не извлечены.
                    </p>
                  )}
                </section>
              )}
              {section === "matrix" && (
                <section className="panel">
                  <h2>Матрица требований</h2>
                  {matrixRows.length ? (
                    <EvidenceObject value={{ rows: matrixRows }} />
                  ) : (
                    <p className="empty-state">Матрица ещё не сформирована.</p>
                  )}
                  {profile ? (
                    <>
                      <h3>Нормативные основания</h3>
                      <p>
                        Учитываются только положения подтверждённых редакций.
                        Неуточнённые основания показаны отдельно.
                      </p>
                      <NormativeRequirementList
                        title="Требуемые разделы ПД"
                        values={profile.required_pd_sections}
                      />
                      <NormativeRequirementList
                        title="Ожидаемые комплекты РД"
                        values={profile.expected_rd_sets}
                      />
                      <GapList
                        gaps={profileGaps.map(
                          (item) => item.code ?? "NORMATIVE_GAP",
                        )}
                      />
                    </>
                  ) : (
                    <p className="empty-state">
                      Подтверждённые нормативные основания для этой модели ещё
                      не определены.
                    </p>
                  )}
                </section>
              )}
              {section === "gaps" && (
                <section className="panel">
                  <h2>Расхождения и пробелы</h2>
                  <a
                    className="button-link"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-analysis.zip`}
                  >
                    Скачать Tender-пакет анализа
                  </a>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-findings.csv`}
                  >
                    Скачать редактируемый график наблюдений
                  </a>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-findings.docx`}
                  >
                    Скачать редактируемый Tender-отчёт
                  </a>
                  <a
                    className="button-link secondary"
                    href={`/api/v1/workspaces/${workspaceId}/project-understanding/tender-document-coverage.csv`}
                  >
                    Скачать покрытие документов
                  </a>
                  {value.defects.length ? (
                    <TenderFindingList
                      defects={value.defects}
                      workspaceId={workspaceId}
                      modeSlug={mode}
                    />
                  ) : materializationState === "complete" ? (
                    <p>
                      По сформированной модели открытые расхождения не
                      зарегистрированы.
                    </p>
                  ) : (
                    <p>
                      Анализ расхождений ещё не завершён; отсутствие записей не
                      означает, что документы не содержат расхождений.
                    </p>
                  )}
                  <GapList gaps={(definition.gaps ?? []).map(humanizeGap)} />
                  <GapList
                    gaps={profileGaps.map(
                      (item) => item.code ?? "NORMATIVE_GAP",
                    )}
                  />
                </section>
              )}
            </>
          );
        }}
      </QueryState>
    </Page>
  );
}

function TenderInputAssessmentTable({
  items,
  workspaceId,
  modeSlug,
}: {
  items: Record<string, unknown>[];
  workspaceId: string;
  modeSlug?: string | undefined;
}) {
  const categoryLabels: Record<string, string> = {
    design_or_working_documentation: "Проектная и рабочая документация",
    quantity_or_estimate: "Ведомость объёмов или смета",
    draft_contract: "Проект договора",
    customer_regulation: "Регламент заказчика",
    specifications: "Спецификации материалов и оборудования",
  };
  const stateLabels: Record<string, string> = {
    available: "Доступно для анализа",
    classification_incomplete: "Обработка классификации не завершена",
    not_detected_in_classified_sources: "Не обнаружено среди классифицированных источников",
  };
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Входные данные</th>
            <th>Статус</th>
            <th>Использование и ограничение</th>
            <th>Источники</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const locators = Array.isArray(item.source_locator_ids)
              ? item.source_locator_ids.map(String)
              : [];
            const sourceNames = Array.isArray(item.source_names)
              ? item.source_names.map(String)
              : [];
            const state = displayValue(item.state, "classification_incomplete");
            return (
              <tr key={displayValue(item.category, "tender-input")}>
                <td>
                  <strong>
                    {categoryLabels[displayValue(item.category)] ??
                      displayValue(item.category)}
                  </strong>
                </td>
                <td>
                  <StatusPill tone={state === "available" ? "default" : "warning"}>
                    {stateLabels[state] ?? state}
                  </StatusPill>
                </td>
                <td>
                  {state === "available"
                    ? "Исходные данные можно использовать в указанной проверке."
                    : displayValue(item.practical_limitation, "Ограничение не описано.")}
                </td>
                <td>
                  {sourceNames.length ? sourceNames.join(", ") : "—"}
                  {locators.length > 0 && (
                    <p>
                      {locators.map((locator, index) => (
                        <span key={locator}>
                          {index > 0 ? ", " : ""}
                          <Link
                            to={workspaceRouteFromSlug(
                              modeSlug,
                              workspaceId,
                              `/evidence/locators/${locator}`,
                            )}
                          >
                            открыть фрагмент
                          </Link>
                        </span>
                      ))}
                    </p>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StructureCandidateList({
  nodes,
  relationships,
  dossiers,
  components,
  identityCandidates,
  workspaceId,
  modeSlug,
}: {
  nodes: Record<string, unknown>[];
  relationships: Record<string, unknown>[];
  dossiers: Record<string, unknown>[];
  components: Record<string, unknown>[];
  identityCandidates: Record<string, unknown>[];
  workspaceId: string;
  modeSlug?: string | undefined;
}) {
  const [filter, setFilter] = useState("");
  const [visibleNodeCount, setVisibleNodeCount] = useState(200);
  const [visibleRelationshipCount, setVisibleRelationshipCount] = useState(200);
  const kindLabels: Record<string, string> = {
    local_area: "Локальная площадка или участок",
    facility: "Объект или сооружение",
    excavation_pit: "Котлован",
    structure: "Сооружение или конструкция",
    zone: "Зона или участок",
  };
  const relationshipLabels: Record<string, string> = {
    contains: "содержит",
    located_in: "расположен в",
    serves: "обслуживает",
    connects_to: "соединён с",
    depends_on: "зависит от",
  };
  if (!nodes.length && !relationships.length && !identityCandidates.length)
    return (
      <p className="empty-state">Структурные кандидаты ещё не извлечены.</p>
    );
  const normalizedFilter = filter.trim().toLocaleLowerCase("ru-RU");
  const matchesFilter = (values: unknown[]) =>
    !normalizedFilter ||
    values.some((value) =>
      displayValue(value, "")
        .toLocaleLowerCase("ru-RU")
        .includes(normalizedFilter),
    );
  const filteredNodes = nodes.filter((node) =>
    matchesFilter([node.raw_name, node.normalized_name, node.node_kind]),
  );
  const filteredRelationships = relationships.filter((relationship) =>
    matchesFilter([
      relationship.subject_raw_name,
      relationship.object_raw_name,
      relationship.relationship_kind,
    ]),
  );
  const visibleNodes = filteredNodes.slice(0, visibleNodeCount);
  const visibleRelationships = filteredRelationships.slice(
    0,
    visibleRelationshipCount,
  );
  return (
    <div className="candidate-list">
      {identityCandidates.length > 0 && (
        <>
          <h3>Междокументные группы-кандидаты</h3>
          <p>
            Эти группы предложены по исходным фрагментам разных документов. Они
            не являются подтверждёнными фактами и не объединяют одноимённые
            элементы автоматически.
          </p>
          <div className="card-grid">
            {identityCandidates.slice(0, visibleNodeCount).map((candidate) => {
              const locators = Array.isArray(candidate.source_locator_ids)
                ? candidate.source_locator_ids.map(String)
                : [];
              return (
                <article
                  className="candidate-row"
                  key={`identity:${displayValue(candidate.identity_candidate_id)}`}
                >
                  <strong>
                    {kindLabels[displayValue(candidate.identity_kind)] ??
                      "Структурная группа"}
                  </strong>
                  <p>
                    {displayValue(
                      candidate.canonical_label,
                      "Наименование не извлечено",
                    )}
                  </p>
                  <small>
                    Кандидат; наблюдений:{" "}
                    {Array.isArray(candidate.member_structure_node_ids)
                      ? candidate.member_structure_node_ids.length
                      : 0}
                    ; уверенность:{" "}
                    {displayValue(candidate.confidence, "не указана")}
                  </small>
                  {locators.slice(0, 4).map((locator) => (
                    <Link
                      key={locator}
                      to={workspaceRouteFromSlug(
                        modeSlug,
                        workspaceId,
                        `/evidence/locators/${locator}`,
                      )}
                    >
                      Открыть исходный фрагмент
                    </Link>
                  ))}
                </article>
              );
            })}
          </div>
        </>
      )}
      {dossiers.length > 0 && (
        <>
          <h3>Карточки площадок и сооружений</h3>
          <p>
            Каждая карточка — отдельное исходно-связанное наблюдение. Совпадения
            наименований в других документах пока не объединяются автоматически.
          </p>
          <div className="card-grid">
            {dossiers.slice(0, visibleNodeCount).map((dossier) => {
              const node = (dossier.structure_node ?? {}) as Record<
                string,
                unknown
              >;
              const locator = displayValue(node.source_locator_id, "");
              const kind = displayValue(node.node_kind, "structure");
              const linked = Array.isArray(dossier.relationships)
                ? dossier.relationships.length
                : 0;
              const linkedWorks = Array.isArray(dossier.linked_work_observations)
                ? (dossier.linked_work_observations as Record<string, unknown>[])
                : [];
              return (
                <article
                  className="candidate-row"
                  key={`dossier:${displayValue(node.structure_node_id)}`}
                >
                  <strong>{kindLabels[kind] ?? "Структурный элемент"}</strong>
                  <p>
                    {displayValue(node.raw_name, "Наименование не извлечено")}
                  </p>
                  <small>
                    Кандидат; связей с тем же исходным фрагментом: {linked}
                  </small>
                  {linkedWorks.length > 0 && (
                    <p>
                      <small>
                        Наблюдения работ в том же исходном фрагменте: {" "}
                        {linkedWorks
                          .slice(0, 4)
                          .map((work) => displayValue(work.work_name, "Работа"))
                          .join("; ")}
                        . Это связь по общему источнику, а не подтверждённое
                        назначение работы сооружению.
                      </small>
                    </p>
                  )}
                  {locator && (
                    <Link
                      to={workspaceRouteFromSlug(
                        modeSlug,
                        workspaceId,
                        `/evidence/locators/${locator}`,
                      )}
                    >
                      Открыть исходный фрагмент
                    </Link>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
      {components.length > 0 && (
        <>
          <h3>Связанные исходные наблюдения</h3>
          <p>
            Эти группы построены только по связям, чьи оба конца извлечены из
            одного исходного фрагмента. Это кандидаты, а не объединённые объекты
            проекта.
          </p>
          <div className="card-grid">
            {components.slice(0, visibleNodeCount).map((component) => {
              const nodes = Array.isArray(component.nodes)
                ? (component.nodes as Record<string, unknown>[])
                : [];
              const relationships = Array.isArray(component.relationships)
                ? component.relationships
                : [];
              const locatorIds = Array.isArray(component.source_locator_ids)
                ? component.source_locator_ids.map((item) =>
                    displayValue(item, ""),
                  )
                : [];
              return (
                <article
                  className="candidate-row"
                  key={displayValue(component.component_key)}
                >
                  <strong>Исходно-связанная группа</strong>
                  <p>
                    {nodes
                      .map((node) =>
                        displayValue(node.raw_name, "Без наименования"),
                      )
                      .join(" → ")}
                  </p>
                  <small>
                    Кандидат; элементов: {nodes.length}, связей:{" "}
                    {relationships.length}
                  </small>
                  {locatorIds.length > 0 && (
                    <p>
                      {locatorIds.map((locatorId) => (
                        <Link
                          key={locatorId}
                          to={workspaceRouteFromSlug(
                            modeSlug,
                            workspaceId,
                            `/evidence/locators/${locatorId}`,
                          )}
                        >
                          Открыть исходный фрагмент
                        </Link>
                      ))}
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
      <h3>Структурные кандидаты</h3>
      <p>
        Это сведения, извлечённые из исходных документов. Они не являются
        подтверждёнными фактами до reconciliation; одинаковые упоминания в
        разных разделах могут относиться к одному объекту.
      </p>
      <label className="field-label">
        Поиск по наименованию или виду
        <input
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value);
            setVisibleNodeCount(200);
            setVisibleRelationshipCount(200);
          }}
          placeholder="Например: КНС, ЛОС или котлован"
        />
      </label>
      <p className="candidate-list-summary">
        Показано структур: {visibleNodes.length} из {filteredNodes.length}.
      </p>
      {visibleNodes.map((node) => {
        const identity = displayValue(node.structure_node_id);
        const locator = displayValue(node.source_locator_id, "");
        const kind = displayValue(node.node_kind, "structure");
        return (
          <article
            className="candidate-row"
            key={`${identity}:${displayValue(node.version)}`}
          >
            <div>
              <strong>{kindLabels[kind] ?? "Структурный элемент"}</strong>
              <p>{displayValue(node.raw_name, "Наименование не извлечено")}</p>
              <small>
                {humanizeStatus(displayValue(node.status, "candidate"))}
              </small>
              {locator && (
                <Link
                  to={workspaceRouteFromSlug(
                    modeSlug,
                    workspaceId,
                    `/evidence/locators/${locator}`,
                  )}
                >
                  Открыть исходный фрагмент
                </Link>
              )}
            </div>
          </article>
        );
      })}
      {visibleNodes.length < filteredNodes.length && (
        <button
          type="button"
          className="ghost"
          onClick={() => setVisibleNodeCount((count) => count + 200)}
        >
          Показать ещё структуры
        </button>
      )}
      {relationships.length > 0 && (
        <>
          <h3>Связи между структурными кандидатами</h3>
          <p>
            Связи показаны как извлечённые наблюдения. Имена ещё не объединяются
            автоматически с одноимёнными объектами из других документов.
          </p>
          <p className="candidate-list-summary">
            Показано связей: {visibleRelationships.length} из{" "}
            {filteredRelationships.length}.
          </p>
          {visibleRelationships.map((relationship) => {
            const identity = displayValue(
              relationship.relationship_candidate_id,
            );
            const locator = displayValue(relationship.source_locator_id, "");
            const kind = displayValue(relationship.relationship_kind, "");
            return (
              <article className="candidate-row" key={identity}>
                <div>
                  <strong>
                    {displayValue(relationship.subject_raw_name)}{" "}
                    {relationshipLabels[kind] ?? "связан с"}{" "}
                    {displayValue(relationship.object_raw_name)}
                  </strong>
                  <small>
                    {humanizeStatus(
                      displayValue(relationship.status, "candidate"),
                    )}
                  </small>
                  {locator && (
                    <Link
                      to={workspaceRouteFromSlug(
                        modeSlug,
                        workspaceId,
                        `/evidence/locators/${locator}`,
                      )}
                    >
                      Открыть исходный фрагмент
                    </Link>
                  )}
                </div>
              </article>
            );
          })}
          {visibleRelationships.length < filteredRelationships.length && (
            <button
              type="button"
              className="ghost"
              onClick={() =>
                setVisibleRelationshipCount((count) => count + 200)
              }
            >
              Показать ещё связи
            </button>
          )}
        </>
      )}
    </div>
  );
}

function CandidateReviewTable({
  kind,
  candidates,
  decisions,
  workspaceId,
  modeSlug,
  onReview,
  pending,
}: {
  kind: "project_field" | "work_type" | "quantity" | "material";
  candidates: Record<string, unknown>[];
  decisions: Record<string, unknown>[];
  workspaceId: string;
  modeSlug?: string | undefined;
  onReview: (payload: {
    candidate_kind: "project_field" | "work_type" | "quantity" | "material";
    candidate_id: string;
    candidate_version: number;
    action: "confirmed" | "rejected" | "corrected";
    resolved_value: string | number | boolean | null;
    reason: string;
  }) => void;
  pending: boolean;
}) {
  const [filter, setFilter] = useState("");
  const [visibleCount, setVisibleCount] = useState(100);
  const titles = {
    project_field: "Общие сведения",
    work_type: "Виды работ",
    quantity: "Объёмы",
    material: "Материалы",
  };
  if (!candidates.length)
    return <p className="empty-state">{titles[kind]} ещё не извлечены.</p>;
  const normalizedFilter = filter.trim().toLocaleLowerCase("ru-RU");
  const filteredCandidates = candidates.filter((candidate) =>
    !normalizedFilter
      ? true
      : [candidate.label, candidate.value, candidate.normalized_value]
          .map((value) => displayValue(value, "").toLocaleLowerCase("ru-RU"))
          .some((value) => value.includes(normalizedFilter)),
  );
  const visibleCandidates = filteredCandidates.slice(0, visibleCount);
  return (
    <div className="candidate-list">
      <h3>{titles[kind]}</h3>
      <p>
        Это исходно связанные кандидаты, а не подтверждённые факты. Показано:{" "}
        {visibleCandidates.length} из {filteredCandidates.length}.
      </p>
      <label className="field-label">
        Поиск по наименованию или значению
        <input
          value={filter}
          onChange={(event) => {
            setFilter(event.target.value);
            setVisibleCount(100);
          }}
          placeholder="Например: котлован, шпунт или м³"
        />
      </label>
      {visibleCandidates.map((candidate) => {
        const identity = String(candidate.candidate_id);
        const decision = decisions.find(
          (item) => String(item.candidate_id) === identity,
        );
        return (
          <CandidateReviewRow
            key={`${identity}:${String(candidate.version)}`}
            kind={kind}
            candidate={candidate}
            decision={decision}
            workspaceId={workspaceId}
            modeSlug={modeSlug}
            onReview={onReview}
            pending={pending}
          />
        );
      })}
      {visibleCandidates.length < filteredCandidates.length && (
        <button
          type="button"
          className="ghost"
          onClick={() => setVisibleCount((count) => count + 100)}
        >
          Показать ещё
        </button>
      )}
    </div>
  );
}

function CandidateReviewRow({
  kind,
  candidate,
  decision,
  workspaceId,
  modeSlug,
  onReview,
  pending,
}: {
  kind: "project_field" | "work_type" | "quantity" | "material";
  candidate: Record<string, unknown>;
  decision?: Record<string, unknown> | undefined;
  workspaceId: string;
  modeSlug?: string | undefined;
  onReview: (payload: {
    candidate_kind: "project_field" | "work_type" | "quantity" | "material";
    candidate_id: string;
    candidate_version: number;
    action: "confirmed" | "rejected" | "corrected";
    resolved_value: string | number | boolean | null;
    reason: string;
  }) => void;
  pending: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [corrected, setCorrected] = useState(displayValue(candidate.value, ""));
  const [reason, setReason] = useState("");
  const locator = displayValue(candidate.source_locator_id, "");
  const submit = (action: "confirmed" | "rejected" | "corrected") => {
    onReview({
      candidate_kind: kind,
      candidate_id: displayValue(candidate.candidate_id),
      candidate_version: Number(candidate.version),
      action,
      resolved_value: action === "corrected" ? corrected : null,
      reason:
        reason ||
        (action === "confirmed"
          ? "Проверено по исходному фрагменту"
          : "Отклонено при проверке"),
    });
    setEditing(false);
  };
  return (
    <article className="candidate-row">
      <div>
        <strong>{displayValue(candidate.label, "Сведение")}</strong>
        <p>{displayValue(candidate.value)}</p>
        <small>
          {humanizeStatus(displayValue(candidate.status, "candidate"))}
        </small>
        {locator && (
          <Link
            to={workspaceRouteFromSlug(
              modeSlug,
              workspaceId,
              `/evidence/locators/${locator}`,
            )}
          >
            Открыть исходный фрагмент
          </Link>
        )}
      </div>
      <div className="candidate-actions">
        {decision ? (
          <StatusPill
            tone={decision.action === "rejected" ? "warning" : "default"}
          >
            {humanizeStatus(String(decision.action))}
          </StatusPill>
        ) : (
          <>
            <button
              type="button"
              className="ghost"
              disabled={pending}
              onClick={() => submit("confirmed")}
            >
              Подтвердить
            </button>
            <button
              type="button"
              className="ghost"
              disabled={pending}
              onClick={() => setEditing(true)}
            >
              Исправить
            </button>
            <button
              type="button"
              className="ghost"
              disabled={pending}
              onClick={() => submit("rejected")}
            >
              Отклонить
            </button>
          </>
        )}
      </div>
      {editing && (
        <div className="candidate-edit">
          <label>
            Исправленное значение
            <input
              value={corrected}
              onChange={(event) => setCorrected(event.target.value)}
            />
          </label>
          <label>
            Причина изменения
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
            />
          </label>
          <button
            type="button"
            disabled={pending || reason.trim().length < 3 || !corrected.trim()}
            onClick={() => submit("corrected")}
          >
            Сохранить новую версию
          </button>
        </div>
      )}
    </article>
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
                  "Требование",
                )}
              </strong>
              <p>Редакция: {displayValue(row.normative_edition_id)}</p>
              <p>Пункт: {displayValue(row.structural_path)}</p>
              <p>Место в источнике: {displayValue(row.locator)}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">
          Подтверждённое нормативное основание пока не определено.
        </p>
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
  const observations = Number(packageValue.candidate_observation_count ?? 1);
  const quantities = Array.isArray(packageValue.quantities)
    ? packageValue.quantities.length
    : 0;
  const materials = Array.isArray(packageValue.materials)
    ? packageValue.materials.length
    : 0;
  const uncertainties = Array.isArray(packageValue.uncertainties)
    ? packageValue.uncertainties.map(String)
    : [];
  return (
    <article className="entity-card">
      <h3>{displayValue(workType.normalized, "Не определён")}</h3>
      <p>
        Наблюдений: {observations.toString()}; объёмов: {quantities.toString()};
        материалов: {materials.toString()}.
      </p>
      {uncertainties.length > 0 && <GapList gaps={uncertainties} />}
      <p>
        Источники:{" "}
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

function TenderFindingList({
  defects,
  workspaceId,
  modeSlug,
}: {
  defects: Record<string, unknown>[];
  workspaceId: string;
  modeSlug?: string | undefined;
}) {
  const labels: Record<string, string> = {
    project_work_missing_in_estimate:
      "Проектная работа требует сопоставления со сметой",
    quantity_mismatch: "Требуется сверка объёма по источникам",
    project_material_missing_in_estimate:
      "Материал требует сопоставления со сметой",
    estimate_material_comparison_input_unavailable:
      "Сопоставление материалов со сметой ещё не выполнено",
    material_quantity_comparison_input_unavailable:
      "Недостаточно данных для сверки количества материала",
    material_quantity_mismatch:
      "Требуется сверка количества материала по источникам",
    estimate_position_unsupported_by_project:
      "Сметная позиция не подтверждена проектным источником",
    incompatible_units: "Единицы измерения требуют проверки",
    ambiguous_source_match: "Связь между исходными сведениями неоднозначна",
    drawing_intelligence_required:
      "Для вывода требуется разбор чертежа или схемы",
    normative_authority_unavailable:
      "Нормативное основание для проверки недоступно",
    rule_coverage_unavailable:
      "Детерминированное правило для проверки недоступно",
    estimate_comparison_input_unavailable:
      "Сопоставление с ведомостью объёмов или сметой ещё не выполнено",
  };
  return (
    <div className="candidate-list">
      <p>
        Это предварительные Tender-наблюдения по источникам. Они не означают
        подтверждённое нарушение, пропуск в смете или окончательное решение.
      </p>
      {defects.map((defect) => {
        const id = displayValue(defect.defect_id, "наблюдение");
        const kind = displayValue(defect.defect_kind, "");
        const locators = Array.isArray(defect.source_locator_ids)
          ? defect.source_locator_ids.map(String)
          : [];
        const subject = displayValue(defect.subject_identity, "Не указан");
        const related = displayValue(defect.related_identity, "");
        const parameters =
          defect.parameters && typeof defect.parameters === "object"
            ? (defect.parameters as Record<string, unknown>)
            : {};
        const missingInput = displayValue(parameters.missing_input, "");
        const consequence = displayValue(parameters.consequence, "");
        const projectValue = displayValue(parameters.project, "");
        const estimateValue = displayValue(parameters.estimate, "");
        const sharedUnit = displayValue(parameters.unit, "");
        const projectUnit = displayValue(parameters.project_unit, "");
        const estimateUnit = displayValue(parameters.estimate_unit, "");
        const difference = displayValue(parameters.difference, "");
        const comparisonCode = displayValue(parameters.code, "");
        const comparisonDetails =
          projectValue || estimateValue
            ? `Проект: ${projectValue || "не указано"}${
                sharedUnit ? ` ${sharedUnit}` : ""
              }; смета: ${estimateValue || "не указано"}${
                sharedUnit ? ` ${sharedUnit}` : ""
              }${
                difference ? `; разница (проект минус смета): ${difference}${
                  sharedUnit ? ` ${sharedUnit}` : ""
                }` : ""
              }.`
            : projectUnit || estimateUnit
              ? `Единицы: проект — ${projectUnit || "не указано"}; смета — ${
                  estimateUnit || "не указано"
                }.`
              : comparisonCode
                ? `Сопоставление не разрешено: ${comparisonCode}.`
                : "";
        return (
          <article className="candidate-row" key={id}>
            <div>
              <strong>{labels[kind] ?? "Требуется инженерская сверка"}</strong>
              <p>
                Объект: {subject}
                {related ? `; связано с: ${related}` : ""}.
              </p>
              <small>
                {humanizeStatus(displayValue(defect.status, "open"))}
              </small>
              {missingInput ? <p>Нужные данные: {missingInput}.</p> : null}
              {consequence ? <p>Последствие: {consequence}.</p> : null}
              {comparisonDetails ? <p>{comparisonDetails}</p> : null}
              {locators.length > 0 && (
                <p>
                  Источники:{" "}
                  {locators.map((locator, index) => (
                    <span key={locator}>
                      {index > 0 ? ", " : ""}
                      <Link
                        to={workspaceRouteFromSlug(
                          modeSlug,
                          workspaceId,
                          `/evidence/locators/${locator}`,
                        )}
                      >
                        открыть фрагмент
                      </Link>
                    </span>
                  ))}
                </p>
              )}
            </div>
          </article>
        );
      })}
    </div>
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
            <dt>{humanizeFieldKey(key)}</dt>
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

function pilotItemStatus(item: Record<string, unknown>) {
  const resolution = displayValue(item.effective_resolution_status);
  if (["accepted", "excluded"].includes(resolution)) return resolution;
  return displayValue(
    item.effective_status ?? item.status,
    "requires_clarification",
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
              <div className="metrics">
                <Metric
                  label="Нормативных документов"
                  value={Number(value.ntd_inventory.total_documents ?? 0)}
                />
                <Metric
                  label="Официальных источников"
                  value={Number(value.ntd_inventory.official_documents ?? 0)}
                />
                <Metric
                  label="Справочных источников"
                  value={Number(value.ntd_inventory.reference_documents ?? 0)}
                />
                <Metric
                  label="Доступны для поиска"
                  value={
                    Number(value.ntd_inventory.searchable ?? 0) +
                    Number(value.ntd_inventory.partially_searchable ?? 0)
                  }
                />
                <Metric
                  label="Bytes присутствуют"
                  value={Number(value.ntd_inventory.bytes_present ?? 0)}
                />
                <Metric
                  label="Структурированных редакций"
                  value={Number(value.ntd_inventory.structured_editions ?? 0)}
                />
                <Metric
                  label="Проверенных положений"
                  value={Number(value.ntd_inventory.verified_provisions ?? 0)}
                />
                <Metric
                  label="Без пригодного текста"
                  value={Number(
                    value.ntd_inventory.documents_without_text ?? 0,
                  )}
                />
                <Metric
                  label="Отсутствующих identities"
                  value={Number(value.ntd_inventory.absent_identities ?? 0)}
                />
              </div>
              <p>
                Полностью доступны для поиска:{" "}
                {Number(value.ntd_inventory.searchable ?? 0)}; частично
                доступны:{" "}
                {Number(value.ntd_inventory.partially_searchable ?? 0)}.
                Актуальность редакции не проверена для{" "}
                {Number(value.ntd_inventory.edition_currency_unchecked ?? 0)}{" "}
                документов.
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
                  <h2>Реализовано</h2>
                  <GapList gaps={value.implemented} good />
                </section>
                <section className="panel">
                  <h2>Ограничения</h2>
                  <GapList gaps={value.blockers} />
                </section>
                <section className="panel">
                  <h2>Решения о готовности</h2>
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
                  <h2>Развёртывание</h2>
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
  if (value.toLowerCase().includes("candidate")) return "Требует подтверждения";
  const labels: Record<string, string> = {
    ACTIVE: "В работе",
    active: "Действует",
    complete: "Обработан",
    partial_with_capability_gap: "Требует дополнения",
    failed: "Ошибка",
    queued: "В очереди",
    paused: "Приостановлено",
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
    pending: "Ожидает загрузки",
    duplicate: "Повторный файл",
    processing: "Обрабатывается",
    candidate: "Требует подтверждения",
    "candidate or verified workspace fact": "Требует подтверждения",
    needs_evidence: "Недостаточно данных",
    conflict: "Обнаружено расхождение",
    quarantined: "Помещён в карантин",
    unsupported: "Не поддерживается",
    confirmed: "Подтверждено",
    corrected: "Исправлено",
    rejected: "Отклонено",
    accepted: "Принято",
    excluded: "Исключено",
    status_changed: "Статус изменён",
    commented: "Добавлен комментарий",
    draft_with_open_questions: "Проект с нерешёнными вопросами",
    reviewed_draft: "Рассмотренный проект",
    requires_clarification: "Требуется уточнение",
    cannot_prepare: "Невозможно подготовить",
    conforms: "Соответствует",
    original_or_finalized: "Финализированный документ",
    recoverable_draft: "Можно подготовить проект",
  };
  return labels[value] ?? value.replaceAll("_", " ").toLowerCase();
}

function humanizeAuditPreflightState(value: string) {
  const labels: Record<string, string> = {
    not_formed: "Комплект не сформирован",
    missing: "Отсутствует в комплекте",
    generated_candidate: "Подготовлен кандидат",
    awaiting_audit: "Ожидает независимого аудита",
    unresolved_requirement: "Требование не определено",
    blocked: "Заблокировано",
    conflict: "Есть расхождение",
    indeterminate: "Недостаточно доказательств",
  };
  return labels[value] ?? humanizeStatus(value);
}

function humanizeAuditDeltaKind(value: string) {
  const labels: Record<string, string> = {
    document: "Состав и содержание документов",
    causal_readiness: "Готовность причин и доказательств",
    package_signing_handover: "Комплект, подписание и передача",
  };
  return labels[value] ?? value;
}

function humanizeAuditCorrection(value: string) {
  const labels: Record<string, string> = {
    form_id_package_from_current_requirement_matrix:
      "Сформировать комплект по текущей матрице требований",
    resolve_requirement_basis_before_package_formation:
      "Уточнить основание требования до формирования комплекта",
    prepare_or_attach_required_document_with_source_evidence:
      "Подготовить или приложить документ с исходными доказательствами",
    resolve_package_or_evidence_blocker:
      "Устранить блокер комплекта или доказательств",
    reconcile_conflicting_package_membership_or_evidence:
      "Сверить конфликтующий состав комплекта или доказательства",
    perform_independent_audit_of_generated_candidate:
      "Провести независимый аудит подготовленного кандидата",
    perform_independent_audit_of_finalized_document:
      "Провести независимый аудит финализированного документа",
    reconcile_package_membership_and_evidence_lineage:
      "Сверить состав комплекта и происхождение доказательств",
    investigate_preflight_state: "Исследовать состояние предварительной сверки",
  };
  return labels[value] ?? humanizeStatus(value);
}

function humanizeAuditConsequence(value: string) {
  const labels: Record<string, string> = {
    required_completeness_cannot_be_compared_to_a_package:
      "комплектность нельзя сопоставить с комплектом",
    required_document_composition_is_not_authoritatively_established:
      "обязательный состав документов не установлен",
    required_document_is_not_available_for_independent_audit:
      "требуемый документ недоступен для независимого аудита",
    package_position_cannot_be_relied_on_until_the_blocker_is_resolved:
      "на позицию комплекта нельзя опираться до устранения блокера",
    conflicting_package_evidence_prevents_a_single_completeness_conclusion:
      "конфликтующие доказательства не позволяют сделать единый вывод о комплектности",
    candidate_presence_is_not_an_independent_content_audit:
      "наличие кандидата не является независимым аудитом содержания",
    finalization_is_not_an_independent_content_audit:
      "финализация не является независимым аудитом содержания",
    package_membership_does_not_yet_support_a_completeness_conclusion:
      "состав комплекта пока не подтверждает вывод о комплектности",
    preflight_state_requires_investigation:
      "состояние предварительной сверки требует исследования",
  };
  return labels[value] ?? humanizeStatus(value);
}

function humanizeRecoveryAction(value: string) {
  const labels: Record<string, string> = {
    review_candidate_against_available_evidence:
      "Проверить подготовленный кандидат по доступным основаниям",
    start_independent_document_audit: "Провести независимую проверку документа",
    collect_missing_source_evidence: "Получить отсутствующие исходные сведения",
    resolve_requirement_authority: "Установить применимое основание требования",
    resolve_evidence_or_relationship:
      "Уточнить доказательства и связь с работой",
  };
  return labels[value] ?? humanizeStatus(value);
}

function humanizeExportKind(value: string) {
  const labels: Record<string, string> = {
    disagreement_protocol: "Протокол разногласий",
    contract_changes: "Предлагаемые изменения к договору",
    requirement_matrix: "Матрица работ и требований",
    id_package: "Комплект исполнительной документации",
    register: "Реестр документов комплекта",
    audit_report: "Отчёт аудита",
    recovery_plan: "План восстановления",
    recovered_drafts: "Проекты восстанавливаемых документов",
    workspace_results: "Архив результатов объекта",
  };
  return labels[value] ?? "Результат объекта";
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

function humanizeJobKind(value: string) {
  const labels: Record<string, string> = {
    DOCUMENT_ADMISSION: "Приём файла",
    DOCUMENT_HASH: "Проверка целостности",
    PDF_INVENTORY: "Учёт страниц",
    NATIVE_TEXT_EXTRACTION: "Извлечение текста",
    DOCUMENT_FORMAT_INVENTORY: "Определение структуры",
    PDF_PAGE_HEALTH_ANALYSIS: "Проверка страниц",
    NATIVE_LAYOUT_EXTRACTION: "Разбор структуры страницы",
    OCR_ROUTING: "Выбор способа обработки",
    OCR_EXTRACTION: "Восстановление текста",
    DOCUMENT_PAGE_CLASSIFICATION: "Классификация документа",
    DOCUMENT_AGGREGATION: "Сборка документа",
    PROJECT_DEFINITION_EXTRACTION: "Сведения об объекте",
    WORK_QUANTITY_MATERIAL_EXTRACTION: "Работы, объёмы и материалы",
    WORK_PACKAGE_ASSEMBLY: "Формирование пакетов работ",
    REQUIREMENT_MATRIX_ASSEMBLY: "Формирование матрицы требований",
    PROJECT_UNDERSTANDING_RECONCILIATION: "Формирование модели объекта",
    ID_DOCUMENT_GENERATION: "Подготовка исполнительного документа",
    EVIDENCE_INDEX_UPDATE: "Связь с исходными фрагментами",
  };
  return labels[value] ?? "Обработка документа";
}

function humanizeExtractionMethod(value: string) {
  const labels: Record<string, string> = {
    native_text: "Из текста исходного документа",
    native: "Из текста исходного документа",
    ocr: "Восстановлено со страницы документа",
    vlm: "Получено при анализе фрагмента; требуется проверка",
    spreadsheet_cell: "Из ячейки таблицы",
    docx_paragraph: "Из абзаца документа",
  };
  return labels[value] ?? "Из исходного документа";
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
    ID_PACKAGE_NOT_FORMED:
      "Комплект исполнительной документации ещё не сформирован.",
    REQUIRED_DOCUMENT_NOT_IN_PACKAGE:
      "Требуемый документ ещё не включён в комплект.",
    GENERATED_CANDIDATE_REQUIRES_AUDIT:
      "Подготовленный кандидат должен пройти независимую проверку.",
    FINALIZED_DOCUMENT_REQUIRES_AUDIT:
      "Финализированный документ ещё не проверен независимым аудитом.",
    REQUIREMENT_AUTHORITY_UNRESOLVED:
      "Полномочие и основание требования ещё не установлены.",
    PACKAGE_MEMBERSHIP_EVIDENCE_INDETERMINATE:
      "Состав комплекта недостаточен для вывода о документе.",
    EXECUTIVE_SCHEME_OUTPUT_BLOCKED:
      "Исполнительная схема не может быть подготовлена без подтверждённой геометрии.",
    QUALITY_DOCUMENTS_MISSING: "Документы о качестве материалов отсутствуют.",
    OCR_REQUIRED: "Для части страниц требуется распознавание.",
    WORK_TYPE_MAPPING_UNRESOLVED:
      "Вид работы ещё не сопоставлен с утверждённым каталогом.",
    WORK_TYPE_MAPPING_AMBIGUOUS:
      "Для вида работы требуется разрешить неоднозначное сопоставление.",
    STRUCTURE_CANDIDATE_RECONCILIATION_PENDING:
      "Структурные кандидаты извлечены, но междокументные связи и идентичности ещё не сверены.",
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
