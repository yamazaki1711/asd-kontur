import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";

const repository = resolve(import.meta.dirname, "../..");
const statePath = process.env.ASD_E2E_STATE_PATH;

test("platform consultant API persists a model answer and restores a durable dialog", async ({
  page,
}) => {
  test.setTimeout(150_000);
  if (!statePath) throw new Error("ASD_E2E_STATE_PATH is required");
  const state = JSON.parse(readFileSync(statePath, "utf8")) as {
    synthetic_qwen_answer?: string | null;
  };
  await page.goto("/login");
  await page.getByLabel("Пользователь").fill("synthetic-live-owner");
  await page.getByLabel("Пароль").fill("Synthetic-Live-Owner-Password-42!");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Строительный консультант" }),
  ).toBeVisible();
  const question =
    process.env.ASD_E2E_EXPECT_CONSULTANT_CITATIONS === "1"
      ? "Какие требования к уходу за бетоном?"
      : "Что проверяют при входном контроле строительных материалов?";
  await page.getByLabel("Ваш вопрос").fill(question);
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().includes("/construction-consultant/conversations/") &&
      response.url().endsWith("/questions"),
    { timeout: 120_000 },
  );
  await page.getByRole("button", { name: "Отправить вопрос" }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBe(true);
  const answer = page.locator(".construction-consultant-message-assistant");
  await expect(answer).toBeVisible({ timeout: 120_000 });
  await expect(answer).not.toHaveText("");
  if (state.synthetic_qwen_answer) {
    await expect(answer.locator(":scope > div")).toHaveText(
      state.synthetic_qwen_answer,
    );
  }
  if (process.env.ASD_E2E_EXPECT_CONSULTANT_CITATIONS === "1") {
    const sources = answer.locator(".construction-consultant-sources");
    await expect(sources).toBeVisible();
    await sources.locator("summary").click();
    await expect(sources.getByRole("link").first()).toBeVisible();
  }
  await page.reload();
  await expect(
    page
      .locator(".construction-consultant-message-user")
      .getByText(question, { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".construction-consultant-message-assistant"),
  ).toHaveCount(1);
});

test("live Support ID package exposes finalized AOSR, register, and provenance", async ({
  page,
}) => {
  test.skip(
    process.env.ASD_E2E_SEED_SUPPORT_PRODUCTION !== "1",
    "support production seed is opt-in",
  );
  if (!statePath) throw new Error("ASD_E2E_STATE_PATH is required");
  const state = JSON.parse(readFileSync(statePath, "utf8")) as {
    support_workspace_id?: string;
  };
  if (!state.support_workspace_id)
    throw new Error("support workspace identity missing");
  await page.goto("/login");
  await page.getByLabel("Пользователь").fill("synthetic-product-owner");
  await page.getByLabel("Пароль").fill("Synthetic-Product-Owner-Password-42!");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  await page.goto(
    `/modes/support/workspaces/${state.support_workspace_id}/support-id`,
  );
  await expect(
    page.getByRole("heading", { name: "Исполнительная документация" }),
  ).toBeVisible();
  await expect(
    page
      .getByText("Акт освидетельствования скрытых работ", { exact: true })
      .first(),
  ).toBeVisible();
  const register = page
    .locator("tbody tr")
    .filter({ hasText: "Реестр документов комплекта" });
  await expect(register.locator("td").first()).toHaveText("1");
  await expect(
    page.getByText("Финализирован", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/форма .* · действует/i)).toBeVisible();
  await expect(page.getByText("печатная форма: Готово к печати")).toBeVisible();
  await expect(page.getByText("проверка: Одобрено")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "История версий комплекта и реестра" }),
  ).toBeVisible();
  for (const version of [1, 2, 3, 4]) {
    await expect(
      page.getByText(`Версия комплекта ${String(version)}`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`Версия реестра ${String(version)}`, { exact: true }),
    ).toBeVisible();
  }
  await expect(page.getByText("Финализировано").first()).toBeVisible();
  await expect(page.getByText("1", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Вид работы").first()).toBeVisible();
  await expect(
    page.getByRole("link", { name: "открыть источник" }).first(),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Скачать финализированный документ" })
    .click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
});

test("live PostgreSQL spine survives worker loss and isolated reset", async ({
  page,
}) => {
  test.setTimeout(90_000);
  if (!statePath) throw new Error("ASD_E2E_STATE_PATH is required");
  const marker = `/tmp/asd-kontur-spine-worker-${String(process.pid)}.marker`;
  let interrupted: ChildProcess | null = null;
  try {
    await page.goto("/login");
    await page.getByLabel("Пользователь").fill("synthetic-live-owner");
    await page.getByLabel("Пароль").fill("Synthetic-Live-Owner-Password-42!");
    await page.getByRole("button", { name: "Войти" }).click();
    await page
      .getByRole("link", { name: "Инженерное сопровождение", exact: true })
      .click();
    await expect(page.getByText("Доступных объектов пока нет.")).toBeVisible();

    await page.getByLabel("Название объекта").fill("Испытательный объект А");
    await page.getByRole("button", { name: "Создать объект" }).click();
    const workspaceACard = page.locator("article").filter({
      has: page.getByRole("heading", { name: "Испытательный объект А" }),
    });
    await page.getByRole("link", { name: "Сменить объект" }).click();
    const workspaceAPath = await workspaceACard
      .getByRole("link", { name: "Открыть" })
      .getAttribute("href");
    if (!workspaceAPath) throw new Error("workspace A link missing");
    const workspaceA = workspaceAPath.split("/").at(-1);
    if (!workspaceA) throw new Error("workspace A identity missing");
    await workspaceACard.getByRole("link", { name: "Открыть" }).click();
    await page.getByRole("link", { name: "Документы", exact: true }).click();
    await page.getByLabel("Выбрать файлы").setInputFiles([
      {
        name: "live-two-pages.pdf",
        mimeType: "application/pdf",
        buffer: syntheticPdf(),
      },
      {
        name: "live-quantities.csv",
        mimeType: "text/csv",
        buffer: syntheticVor(),
      },
    ]);
    await expect(page.getByText("2 файлов")).toBeVisible();
    await page.getByRole("button", { name: "Начать загрузку" }).click();
    await expect(
      page.getByRole("link", { name: "live-two-pages.pdf" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "live-quantities.csv" }),
    ).toBeVisible();

    interrupted = worker("claim-and-pause", marker);
    await expect.poll(() => existsSync(marker), { timeout: 15_000 }).toBe(true);
    interrupted.kill("SIGKILL");
    await exited(interrupted);
    interrupted = null;
    await page.getByRole("link", { name: "Обработка", exact: true }).click();
    await expect(page.getByText("Выполняется")).toBeVisible();
    await page.waitForTimeout(5_500);
    // Two admitted sources now schedule structure reconciliation as an
    // explicit durable stage. The restarted worker therefore completes 29
    // jobs after reclaiming the interrupted lease, and the history table
    // exposes 28 terminal rows in addition to the interrupted attempt.
    const restarted = worker("drain", undefined, 29);
    expect(await exited(restarted)).toBe(0);
    await expect
      .poll(
        async () =>
          page.locator("tbody tr").filter({ hasText: "Завершено" }).count(),
        { timeout: 15_000 },
      )
      .toBe(28);

    await page.getByRole("link", { name: "Документы" }).click();
    await expect(
      page.getByRole("link", { name: "live-two-pages.pdf" }),
    ).toHaveCount(1);
    await page.getByRole("link", { name: "live-two-pages.pdf" }).click();
    await expect(page.getByLabel("Страница PDF 1")).toBeVisible();
    await expect(page.getByLabel("Область исходного фрагмента")).toBeVisible();
    await expect(page.getByText("Состояние сведения")).toBeVisible();
    await expect(page.getByText("Требует уточнения").first()).toBeVisible();

    await page
      .getByRole("link", { name: "Модель объекта", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Модель объекта" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Виды и объёмы работ" }).click();
    await expect(
      page.getByText("Устройство монолитной плиты", { exact: true }),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Открыть исходный фрагмент" })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: "Точное место в исходном документе" }),
    ).toBeVisible();
    await expect(page.getByText("Состояние сведения")).toBeVisible();
    await expect(page.getByText("Требует подтверждения")).toBeVisible();
    await expect(page.getByText("workspace_fact_candidate")).toHaveCount(0);

    for (const [slug, modeName, title, resultMarker] of [
      [
        "tender",
        "Tender",
        "Тендерный анализ",
        "Договор не предоставлен для договорного анализа",
      ],
      [
        "support",
        "Support",
        "Инженерное сопровождение",
        "Матрица работ и требований",
      ],
      ["audit", "Audit", "Аудит", "Отчёт аудита"],
      ["restoration", "Restoration", "Восстановление", "План восстановления"],
    ] as const) {
      await page.goto(`/modes/${slug}/workspaces/${workspaceA}`);
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
      await expect(page.getByText("Доступно частично")).toBeVisible();
      await page.getByRole("link", { name: "Результат режима" }).click();
      const main = page.getByRole("main");
      const formButton = main.getByRole("button", {
        name: "Сформировать результат",
      });
      const resultMarkerText = main.getByText(resultMarker, { exact: true });
      await expect(formButton.or(resultMarkerText)).toBeVisible();
      if (await formButton.isVisible()) {
        const formed = page.waitForResponse(
          (response) =>
            response.request().method() === "POST" &&
            response
              .url()
              .endsWith(`/workspaces/${workspaceA}/modes/${modeName}/result`),
        );
        await formButton.click();
        expect((await formed).ok()).toBe(true);
      }
      await expect(
        main.getByRole("heading", { name: `Результат: ${title}` }),
      ).toBeVisible();
      await expect(resultMarkerText).toBeVisible();
      await expect(
        main.getByText(
          "Актуальность редакций нормативных документов не проверена",
        ),
      ).toBeVisible();
    }
    await page.goto(`/modes/audit/workspaces/${workspaceA}/result`);
    const auditExportCreated = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response
          .url()
          .endsWith(`/workspaces/${workspaceA}/modes/Audit/exports`),
    );
    await page
      .locator(".export-card")
      .filter({ hasText: "Отчёт аудита" })
      .getByRole("button", { name: "Подготовить DOCX" })
      .click();
    expect((await auditExportCreated).ok()).toBe(true);
    const auditLink = page.getByRole("link", {
      name: /Скачать Отчёт аудита \(DOCX\)/,
    });
    await expect(auditLink).toBeVisible();
    const auditDownload = page.waitForEvent("download");
    await auditLink.click();
    expect((await auditDownload).suggestedFilename()).toMatch(/\.docx$/);
    await page.goto(`/modes/tender/workspaces/${workspaceA}/result`);
    await expect(
      page.getByText("Договор не предоставлен для договорного анализа", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText("Протокол разногласий", { exact: true }),
    ).toHaveCount(0);
    const archiveCreated = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response
          .url()
          .endsWith(`/workspaces/${workspaceA}/modes/Tender/exports`),
    );
    await page.getByRole("button", { name: "Подготовить общий архив" }).click();
    expect((await archiveCreated).ok()).toBe(true);
    const archiveLink = page.getByRole("link", {
      name: /Скачать Архив результатов объекта \(ZIP\)/,
    });
    await expect(archiveLink).toBeVisible();
    const archiveDownload = page.waitForEvent("download");
    await archiveLink.click();
    expect((await archiveDownload).suggestedFilename()).toMatch(/\.zip$/);
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1280, height: 720 },
      { width: 390, height: 844 },
      { width: 360, height: 800 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto(`/modes/tender/workspaces/${workspaceA}/result`);
      await expect(
        page.getByText("Договор не предоставлен для договорного анализа", {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByText("Протокол разногласий", { exact: true }),
      ).toHaveCount(0);
      expect(
        await page.evaluate(
          () =>
            globalThis.document.documentElement.scrollWidth ===
            globalThis.document.documentElement.clientWidth,
        ),
      ).toBe(true);
    }
    await page.setViewportSize({ width: 1280, height: 720 });
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
    await expect(
      page.getByRole("heading", {
        name: "NTD Seed Remediation — exact denominator",
      }),
    ).toBeVisible();
    await expect(
      page.locator(".metric").filter({ hasText: "Denominator" }),
    ).toContainText("25");
    await expect(
      page.getByText(
        "sha256:071960850be497aa6cff032a64375f9cacacadc9fed1a36b136fddfb862ca4b6",
      ),
    ).toBeVisible();
    if (process.env.ASD_E2E_EXPECT_NTD_NATIVE_CANARY === "1") {
      const normativeRow = page.locator("tbody tr").filter({
        hasText: "СП 543.1325800.2024",
      });
      await expect(normativeRow).toContainText("6 verified provisions");
      await expect(normativeRow).toContainText("1 Practice↔NTD");
      await expect(normativeRow).toContainText("7.1.13 · page 23");
      await expect(normativeRow).toContainText("edition: not_activated");
      await expect(
        normativeRow.getByRole("link", { name: /Evidence 1: page 23 region/ }),
      ).toHaveAttribute("href", /#page=23$/);
    }

    await page.goto("/modes/support/workspaces");
    await page.getByLabel("Название объекта").fill("Испытательный объект Б");
    await page.getByRole("button", { name: "Создать объект" }).click();
    await page.goto(`/admin/workspaces/${workspaceA}/reset`);
    await page.getByRole("button", { name: "Подготовить reset" }).click();
    const confirmation = await page.locator(".danger-text code").textContent();
    if (!confirmation) throw new Error("reset confirmation missing");
    await page.getByLabel("Подтверждение exact target").fill(confirmation);
    await page.getByRole("button", { name: "Выполнить reset" }).click();
    await page.goto("/modes/support/workspaces");
    await expect(page.getByText("Испытательный объект Б")).toBeVisible();
    await expect(page.getByText("Испытательный объект А")).toHaveCount(0);
    await page.getByRole("button", { name: "Выйти" }).click();
    await expect(
      page.getByRole("heading", { name: "АСД-КОНТУР" }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        async () => (await fetch("/api/v1/workspaces")).status,
      ),
    ).toBe(401);
  } finally {
    interrupted?.kill("SIGKILL");
    if (existsSync(marker)) unlinkSync(marker);
  }
});

function worker(
  mode: "claim-and-pause" | "drain",
  marker?: string,
  expected?: number,
) {
  const arguments_ = [
    "run",
    "python",
    "tools/run_product_spine_e2e_worker.py",
    mode,
  ];
  if (marker) arguments_.push("--marker", marker);
  if (expected !== undefined) arguments_.push("--expected", String(expected));
  return spawn("uv", arguments_, {
    cwd: repository,
    env: process.env,
    stdio: ["ignore", "inherit", "inherit"],
  });
}

async function exited(child: ChildProcess) {
  return new Promise<number | null>((resolveExit, reject) => {
    child.once("error", reject);
    child.once("exit", resolveExit);
  });
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
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`;
  body += offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`)
    .join("");
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\n`;
  body += `startxref\n${String(xref)}\n%%EOF\n`;
  return Buffer.from(body, "ascii");
}

function syntheticVor() {
  return Buffer.from(
    "Ведомость объёмов работ;;;;;\n" +
      "Вид работ;Объём;Ед. изм.;Материал;Количество материала;Ед. изм. материала\n" +
      "Устройство монолитной плиты;+12,350;м³;Бетон В25;12,350;м³\n",
    "utf8",
  );
}
