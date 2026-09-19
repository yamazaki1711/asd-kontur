import { expect, test, type Route } from "@playwright/test";

const workspaceA = "018f5c3e-7b00-7000-8000-000000002101";
const workspaceB = "018f5c3e-7b00-7000-8000-000000002102";
const documentId = "018f5c3e-7b00-7000-8000-000000002103";
const challengeId = "018f5c3e-7b00-7000-8000-000000002104";
const conversationId = "018f5c3e-7b00-7000-8000-000000002105";
const turnId = "018f5c3e-7b00-7000-8000-000000002106";
const timestamp = "2026-08-26T00:00:00+12:00";

test("user enters through four Russian modes and keeps the selected object", async ({
  page,
}) => {
  let loggedIn = false;
  let resetPrepared = false;
  let assistantAsked = false;
  const createdWorkspaces: ReturnType<typeof workspace>[] = [];
  const pdf = syntheticPdf();

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/session/login" && request.method() === "POST") {
      loggedIn = true;
      return json(route, session());
    }
    if (path === "/api/v1/session" && request.method() === "GET") {
      return loggedIn
        ? json(route, session())
        : json(route, error("session_invalid"), 401);
    }
    if (path === "/api/v1/session/logout" && request.method() === "POST") {
      loggedIn = false;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/v1/workspaces" && request.method() === "GET") {
      return loggedIn
        ? json(route, createdWorkspaces)
        : json(route, error("session_invalid"), 401);
    }
    if (path === "/api/v1/workspaces" && request.method() === "POST") {
      const body = request.postDataJSON() as { display_name: string };
      const id = createdWorkspaces.length === 0 ? workspaceA : workspaceB;
      const value = workspace(id, body.display_name);
      createdWorkspaces.push(value);
      return json(route, value, 201);
    }
    if (path === `/api/v1/workspaces/${workspaceA}/lifecycle`) {
      return json(route, workspace(workspaceA, "Synthetic workspace A"));
    }
    if (path === `/api/v1/workspaces/${workspaceB}/lifecycle`) {
      return json(route, workspace(workspaceB, "Synthetic workspace B"));
    }
    if (path.endsWith("/documents") && request.method() === "POST") {
      return json(
        route,
        {
          intake_manifest_id: challengeId,
          manifest_digest: digest("a"),
          accepted_document_ids: [documentId],
          duplicate_document_ids: [],
          rejected_count: 0,
          job_ids: [challengeId],
        },
        202,
      );
    }
    if (path.endsWith("/documents") && request.method() === "GET") {
      return json(route, { items: [document()], next_cursor: null });
    }
    if (path.endsWith(`/documents/${documentId}/content`)) {
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        headers: { "Accept-Ranges": "bytes" },
        body: pdf,
      });
    }
    if (path.endsWith(`/evidence/${documentId}/pages/1`)) {
      return json(route, evidence());
    }
    if (path.endsWith("/jobs")) {
      return json(route, [job()]);
    }
    if (path.endsWith("/events") && !path.includes("/assistant/")) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `id: 1\nevent: job.succeeded\ndata: {"job_id":"${challengeId}","sequence":1,"event_type":"job.succeeded","safe_message_code":"job_succeeded","terminal":true,"recorded_at":"${timestamp}"}\n\n`,
      });
    }
    if (
      path.endsWith("/assistant/conversations") &&
      request.method() === "GET"
    ) {
      return json(route, [
        {
          conversation_id: conversationId,
          workspace_id: workspaceA,
          title: "Рабочий диалог",
          latest_mode: "Support",
          message_count: assistantAsked ? 2 : 0,
          created_at: timestamp,
        },
      ]);
    }
    if (
      path.endsWith("/assistant/conversations") &&
      request.method() === "POST"
    ) {
      return json(
        route,
        {
          conversation_id: conversationId,
          workspace_id: workspaceA,
          title: "Рабочий диалог",
          latest_mode: null,
          message_count: 0,
          created_at: timestamp,
        },
        201,
      );
    }
    if (path.endsWith(`/assistant/conversations/${conversationId}/messages`)) {
      return json(
        route,
        assistantAsked
          ? [
              {
                message_id: documentId,
                conversation_id: conversationId,
                turn_id: turnId,
                ordinal: 1,
                role: "user",
                content: "Какие документы нужны для АОСР?",
                sources: [],
                action_proposals: [],
                created_at: timestamp,
              },
              {
                message_id: challengeId,
                conversation_id: conversationId,
                turn_id: turnId,
                ordinal: 2,
                role: "assistant",
                content:
                  "Для предъявления подготовьте АОСР и подтверждённые приложения.",
                sources: [
                  {
                    source_id: documentId,
                    authority_layer: "methodological_practice",
                    title: "Пособие по исполнительной документации",
                    locator_label: "раздел пособия, страница 20",
                    fragment:
                      "Состав документов определяется выполненной работой.",
                    href: `/api/v1/platform/sources/${documentId}/content#page=20`,
                  },
                ],
                action_proposals: [],
                created_at: timestamp,
              },
            ]
          : [],
      );
    }
    if (path.endsWith(`/assistant/conversations/${conversationId}/turns`)) {
      assistantAsked = true;
      return json(
        route,
        {
          turn_id: turnId,
          conversation_id: conversationId,
          ordinal: 1,
          mode: "Support",
          question: "Какие документы нужны для АОСР?",
          state: "queued",
          failure_code: null,
          project_definition_id: null,
          project_definition_version: null,
          created_at: timestamp,
          started_at: null,
          completed_at: null,
        },
        202,
      );
    }
    if (path.endsWith(`/assistant/turns/${turnId}/events`)) {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body:
          'id: 1\nevent: delta\ndata: {"text":"Для предъявления подготовьте АОСР"}\n\n' +
          `id: 2\nevent: completed\ndata: {"state":"succeeded"}\n\n`,
      });
    }
    if (path.includes("/modes/")) {
      const mode = decodeURIComponent(path.split("/").at(-1) ?? "Tender");
      return json(route, {
        mode,
        purpose: "Bounded synthetic mode fixture",
        available_inputs: ["workspace_documents"],
        execution_id: null,
        execution_state: null,
        matrix_version_id: null,
        bounded_results: {},
        missing_capabilities: ["WORK_REQUIREMENT_MATRIX_UNAVAILABLE"],
        gaps: ["VERIFIED_NTD_SUBSET"],
        readiness: "FOUNDATION_ONLY",
      });
    }
    if (path === "/api/v1/platform/knowledge-status") {
      return json(route, knowledge());
    }
    if (path.endsWith("/lifecycle/reset/prepare")) {
      resetPrepared = true;
      return json(route, {
        challenge_id: challengeId,
        workspace_id: workspaceA,
        target_lifecycle_version: 12,
        confirmation_text: `RESET ${workspaceA} synthetic-confirmation`,
        expires_at: timestamp,
        assurance_profile: "development_single_owner_confirmation",
      });
    }
    if (path.endsWith("/lifecycle/reset/execute") && resetPrepared) {
      const index = createdWorkspaces.findIndex(
        (value) => value.workspace_id === workspaceA,
      );
      if (index >= 0) createdWorkspaces.splice(index, 1);
      return json(route, {
        reset_receipt_id: challengeId,
        workspace_id: workspaceA,
        outcome: "verified",
        deleted_relation_row_count: 12,
        deleted_object_count: 1,
        archive_package_digest: digest("c"),
        platform_fingerprint_before: digest("d"),
        platform_fingerprint_after: digest("d"),
        completed_at: timestamp,
      });
    }
    if (path === "/api/v1/capabilities") {
      return json(route, {
        contract_version: "2.2.0",
        slice: "PRODUCT-APPLICATION-SPINE-01",
        implemented: ["application.http-api"],
        blockers: ["MEMORY_DATA_DEFECT"],
        trial_ready: false,
        oks_ready: false,
        product_ready: false,
      });
    }
    return json(route, error("synthetic_route_not_defined"), 404);
  });

  await page.goto("/login");
  await page.getByLabel("Пользователь").fill("synthetic-owner");
  await page.getByLabel("Пароль").fill("Synthetic-Password-42!");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  const expectedModes = [
    "Тендерный анализ",
    "Инженерное сопровождение",
    "Аудит",
    "Восстановление",
  ];
  const modeSlugs = new Map([
    ["Тендерный анализ", "tender"],
    ["Инженерное сопровождение", "support"],
    ["Аудит", "audit"],
    ["Восстановление", "restoration"],
  ]);
  await expect(page.locator("a.mode-card")).toHaveCount(4);
  await expect(page.locator("a.mode-card a, a.mode-card button")).toHaveCount(
    0,
  );
  await expect(page.getByText("Выбрать режим", { exact: true })).toHaveCount(0);
  for (const title of expectedModes)
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const normalText = await page.locator("main").innerText();
  for (const forbidden of [
    "Product Application Spine",
    "ProductApplication PARTIAL",
    "Workspaces",
    "Platform Knowledge",
    "Operations",
    "Tender",
    "Support",
    "Restoration",
    "Synthetic",
  ])
    expect(normalText).not.toContain(forbidden);

  const supportModeCard = page.getByRole("link", {
    name: "Инженерное сопровождение",
    exact: true,
  });
  await expect(supportModeCard).toHaveCSS("cursor", "pointer");
  await page
    .getByRole("link", { name: "Тендерный анализ", exact: true })
    .focus();
  await page.keyboard.press("Tab");
  await expect(supportModeCard).toBeFocused();
  await expect(supportModeCard).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/modes\/support\/workspaces$/);
  await page.getByLabel("Название объекта").fill("Строительство корпуса А");
  await page.getByRole("button", { name: "Создать объект" }).click();
  await expect(
    page.getByRole("heading", { name: "Инженерное сопровождение" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Инженерный помощник" }).click();
  await expect(page.getByTestId("assistant-panel")).toBeVisible();
  await expect(page.getByTestId("assistant-panel")).toContainText(
    "Инженерное сопровождение",
  );
  await page.getByLabel("Ваш вопрос").fill("Какие документы нужны для АОСР?");
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(
    page.getByText(
      "Для предъявления подготовьте АОСР и подтверждённые приложения.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Пособие по исполнительной документации/ }),
  ).toHaveAttribute("href", new RegExp(`${documentId}/content#page=20`));
  await page.getByRole("button", { name: "Закрыть" }).click();

  for (const title of expectedModes) {
    await page.getByRole("link", { name: "Сменить режим" }).click();
    await page.getByRole("link", { name: title, exact: true }).click();
    await expect(page).toHaveURL(
      new RegExp(`/modes/${String(modeSlugs.get(title))}/workspaces$`),
    );
    await expect(page.getByText("Строительство корпуса А")).toBeVisible();
    await page.getByRole("link", { name: "Открыть" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await page.getByRole("button", { name: "Инженерный помощник" }).click();
    await expect(page.getByTestId("assistant-panel")).toContainText(title);
    await page.getByRole("button", { name: "Закрыть" }).click();
  }
  await page.goto(`/workspaces/${workspaceA}/documents`);
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  await expect(page.locator("a.mode-card")).toHaveCount(4);
  await page.getByRole("link", { name: "Восстановление", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/modes/restoration/workspaces/${workspaceA}/documents$`),
  );
  await page.getByRole("link", { name: "Документы" }).click();
  const chooser = page.getByLabel("Выбрать файлы");
  await chooser.setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await page.getByRole("button", { name: "Начать загрузку" }).click();
  await expect(page.getByRole("link", { name: "synthetic.pdf" })).toBeVisible();
  await page.getByRole("link", { name: "synthetic.pdf" }).click();
  await expect(page.getByLabel("Страница PDF 1")).toBeVisible();
  await expect(page.getByLabel("Область исходного фрагмента")).toBeVisible();
  await page.goto("/admin/knowledge");
  await page.getByText("Технические сведения", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "KnowledgeReady = false" }),
  ).toBeVisible();
  await expect(
    page
      .getByText("Требуется дополнительная проверка или исходные данные.")
      .last(),
  ).toBeVisible();
  await page.goto("/modes/audit/workspaces");
  await page.getByLabel("Название объекта").fill("Строительство корпуса Б");
  await page.getByRole("button", { name: "Создать объект" }).click();
  await expect(page.getByRole("heading", { name: "Аудит" })).toBeVisible();
  await page.goto(`/admin/workspaces/${workspaceA}/reset`);
  await page.getByRole("button", { name: "Подготовить reset" }).click();
  const exact = `RESET ${workspaceA} synthetic-confirmation`;
  await page.getByLabel("Подтверждение exact target").fill(exact);
  await page.getByRole("button", { name: "Выполнить reset" }).click();
  await page.goto("/modes/audit/workspaces");
  await expect(page.getByText("Строительство корпуса Б")).toBeVisible();
  await expect(page.getByText("Строительство корпуса А")).toHaveCount(0);
  await page.getByRole("button", { name: "Выйти" }).click();
  await expect(page.getByRole("heading", { name: "АСД-КОНТУР" })).toBeVisible();
  const unauthorizedStatus = await page.evaluate(async () => {
    const response = await fetch("/api/v1/workspaces");
    return response.status;
  });
  expect(unauthorizedStatus).toBe(401);
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  test(`mode selection has no horizontal overflow at ${String(viewport.width)}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.route("**/api/v1/session", (route) => json(route, session()));
    await page.goto("/modes");
    await expect(page.locator("a.mode-card")).toHaveCount(4);
    expect(
      await page.evaluate(
        () =>
          globalThis.document.documentElement.scrollWidth ===
          globalThis.document.documentElement.clientWidth,
      ),
    ).toBe(true);
  });
}

function workspace(id: string, displayName: string) {
  return {
    organization_id: challengeId,
    workspace_id: id,
    construction_object_id: documentId,
    display_name: displayName,
    lifecycle_state: "ACTIVE",
    lifecycle_version: 2,
    workspace_revision: 1,
    write_fenced: false,
    created_at: timestamp,
  };
}

function session() {
  return {
    owner_identity_id: "owner:synthetic",
    username: "synthetic-owner",
    profile: "development_loopback",
    absolute_expires_at: timestamp,
  };
}

function document() {
  return {
    organization_id: challengeId,
    workspace_id: workspaceA,
    document_id: documentId,
    version: 1,
    prior_versions: [],
    job_ids: [challengeId],
    source_artifact_id: challengeId,
    source_version_id: challengeId,
    safe_display_name: "synthetic.pdf",
    relative_path: "synthetic.pdf",
    media_type: "application/pdf",
    size_bytes: 1024,
    content_digest: digest("a"),
    page_count: 2,
    admission_status: "accepted",
    extraction_status: "partial_with_capability_gap",
    capability_gaps: ["OCR_REQUIRED"],
    recorded_at: timestamp,
  };
}

function job() {
  return {
    organization_id: challengeId,
    workspace_id: workspaceA,
    job_id: challengeId,
    job_kind: "NATIVE_TEXT_EXTRACTION",
    state: "succeeded",
    priority: 1,
    attempt_count: 1,
    max_attempts: 3,
    cancellation_state: "none",
    typed_failure_code: null,
    terminal_receipt_id: challengeId,
    created_at: timestamp,
    started_at: timestamp,
    heartbeat_at: timestamp,
    completed_at: timestamp,
  };
}

function knowledge() {
  return {
    practice_guide_count: 1,
    practice_edition_count: 1,
    active_practice_release_count: 1,
    source_guidance_count: 2410,
    active_intelligence_count: 7113,
    active_playbook_count: 1644,
    active_gap_count: 858,
    conflict_count: 138,
    quarantine_count: 0,
    normative_identity_count: 25,
    verified_normative_edition_count: 0,
    verified_normative_provision_count: 0,
    rule_version_count: 0,
    projection_states: {},
    last_verified_backup_at: null,
    semantic_fingerprints: { active: digest("d") },
    memory_data_defect: true,
    knowledge_ready: false,
    blockers: [
      "MEMORY_DATA_DEFECT",
      "VERIFIED_NTD_UNAVAILABLE",
      "ACTIVE_RULE_VERSION_UNAVAILABLE",
    ],
    ntd_inventory: {
      total_documents: 100,
      official_documents: 50,
      reference_documents: 50,
      searchable: 40,
      partially_searchable: 10,
      bytes_present: 1024,
      structured_editions: 20,
      verified_provisions: 30,
      documents_without_text: 5,
      absent_identities: 2,
      edition_currency_unchecked: 15,
    },
  };
}

function evidence() {
  return {
    locator: {
      document_id: documentId,
      document_version: 1,
      source_version_id: documentId,
      source_locator_id: challengeId,
      page_number: 1,
      region: [0.1, 0.2, 0.6, 0.7],
      width_points: 595,
      height_points: 842,
      rotation_degrees: 0,
      evidence_digest: digest("e"),
      extraction_method: "native_pdf_layout",
    },
    candidate_fact_status: "evidence_only",
    authority_type: "workspace_source",
    rule_version: null,
    practice_release: null,
    normative_edition: null,
    uncertainty: [],
    conflicts: [],
    quarantined: false,
  };
}

function error(code: string) {
  return {
    error: { code, message: code, correlation_id: challengeId, parameters: {} },
  };
}

function digest(character: string) {
  return `sha256:${character.repeat(64)}`;
}

function syntheticPdf() {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources <<>> /Contents 5 0 R >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources <<>> /Contents 6 0 R >>",
    "<< /Length 0 >>\nstream\n\nendstream",
    "<< /Length 0 >>\nstream\n\nendstream",
  ];
  let body = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(body, "ascii"));
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body, "ascii");
  body += `xref\n0 ${String(objects.length + 1)}\n`;
  body += "0000000000 65535 f \n";
  body += offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`)
    .join("");
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\n`;
  body += `startxref\n${String(xref)}\n%%EOF\n`;
  return Buffer.from(body, "ascii");
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}
