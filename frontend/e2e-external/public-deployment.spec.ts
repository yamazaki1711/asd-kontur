import { createHash } from "node:crypto";
import { readdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const website = process.env.ASD_PUBLIC_E2E_WEBSITE_URL;
const username = process.env.ASD_PUBLIC_E2E_USERNAME;
const password = process.env.ASD_PUBLIC_E2E_PASSWORD;
const expectedPdfDigest = process.env.ASD_PUBLIC_E2E_PDF_DIGEST;
const corpusRoot = process.env.ASD_PUBLIC_E2E_CORPUS_ROOT;

if (!website) throw new Error("ASD_PUBLIC_E2E_WEBSITE_URL is required");
if (!username) throw new Error("ASD_PUBLIC_E2E_USERNAME is required");
if (!password) throw new Error("ASD_PUBLIC_E2E_PASSWORD is required");
if (!expectedPdfDigest)
  throw new Error("ASD_PUBLIC_E2E_PDF_DIGEST is required");

test("public website routes to the isolated Product Application", async ({
  page,
}) => {
  await page.goto(website);
  await expect(page).toHaveTitle(/АСД-КОНТУР/);
  await expect(
    page.getByRole("heading", {
      name: "Аудит и инженерное сопровождение строительства",
    }),
  ).toBeVisible();
  const content = await page.locator("body").innerText();
  for (const forbidden of [
    "ИСУИД",
    "24 337",
    "24337",
    "690 томов",
    "AI",
    "ИИ",
    "evidence",
    "Local-first",
    "Tender",
    "Support",
    "Restoration",
    "доказательн",
  ])
    expect(content).not.toContain(forbidden);
  await expect(
    page.getByRole("link", { name: "Войти в комплекс" }).first(),
  ).toHaveAttribute("href", "https://app.asd-kontur.ru");
});

test("authorized user enters by mode and downloads the finalized package document", async ({
  page,
  request,
}) => {
  const unauthorized = await request.get("/api/v1/workspaces");
  expect(unauthorized.status()).toBe(401);

  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "АСД-КОНТУР" })).toBeVisible();
  await page.getByLabel("Пользователь").fill(username);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  await expect(page.locator("a.mode-card")).toHaveCount(4);
  await expect(page.getByText("Выбрать режим", { exact: true })).toHaveCount(0);
  await page
    .getByRole("link", { name: "Инженерное сопровождение", exact: true })
    .click();
  await expect(page).toHaveURL(/\/modes\/support\/workspaces$/);
  const workspace = page
    .locator("article")
    .filter({ hasText: "Демонстрационный объект" })
    .first();
  const target = await workspace
    .getByRole("link", { name: "Открыть" })
    .getAttribute("href");
  if (!target) throw new Error("synthetic workspace link is missing");
  const workspaceId = target.split("/").at(-1);
  if (!workspaceId) throw new Error("synthetic workspace identity is missing");

  for (const path of ["documents", "evidence", "work-matrix"]) {
    await page.goto(`/modes/support/workspaces/${workspaceId}/${path}`);
    await expect(page.locator("main")).toBeVisible();
  }
  for (const [mode, title] of [
    ["tender", "Тендерный анализ"],
    ["support", "Инженерное сопровождение"],
    ["audit", "Аудит"],
    ["restoration", "Восстановление"],
  ] as const) {
    await page.goto(`/modes/${mode}/workspaces/${workspaceId}`);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await page.goto(
      `/modes/${mode}/workspaces/${workspaceId}/project-understanding`,
    );
    await expect(
      page.getByRole("heading", { name: "Модель объекта" }),
    ).toBeVisible();
  }

  await page.goto(`/modes/support/workspaces/${workspaceId}/documents`);
  await expect(
    page.getByRole("link", {
      name: "Пояснительная_записка.docx",
      exact: true,
    }),
  ).toBeVisible();
  const corruptRow = page
    .locator("tbody tr")
    .filter({ hasText: "Поврежденный_документ.pdf" });
  await expect(corruptRow.getByText("Помещён в карантин")).toBeVisible();

  await page.goto(
    `/modes/support/workspaces/${workspaceId}/project-understanding`,
  );
  for (const section of [
    "Общие сведения",
    "Структура объекта",
    "Виды и объёмы работ",
    "Материалы и изделия",
    "Пакеты работ",
    "Матрица требований",
    "Расхождения и пробелы",
  ])
    await expect(page.getByRole("button", { name: section })).toBeVisible();
  await page.getByRole("button", { name: "Виды и объёмы работ" }).click();
  await expect(
    page.getByText("Устройство монолитной плиты", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Открыть исходный фрагмент" })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Точное место в исходном документе" }),
  ).toBeVisible();

  const modeResults = [
    ["tender", "Тендерный анализ", "Протокол разногласий"],
    ["support", "Инженерное сопровождение", "Матрица работ и требований"],
    ["audit", "Аудит", "Отчёт аудита"],
    ["restoration", "Восстановление", "План восстановления"],
  ] as const;
  for (const [mode, title, output] of modeResults) {
    await page.goto(`/modes/${mode}/workspaces/${workspaceId}/result`);
    const form = page.getByRole("button", { name: "Сформировать результат" });
    const outputHeading = page.getByText(output, { exact: true });
    await expect(form.or(outputHeading)).toBeVisible();
    if (await form.isVisible()) await form.click();
    await expect(
      page.getByRole("heading", { name: `Результат: ${title}` }),
    ).toBeVisible();
    await expect(page.getByText(output, { exact: true })).toBeVisible();
    await expect(page.getByText("Актуальность редакций")).toBeVisible();
    await expect(page.getByText("Выводы и действия")).toBeVisible();
  }
  await page.goto(`/modes/audit/workspaces/${workspaceId}/result`);
  const firstAudit = page.locator(".pilot-result-item").first();
  await firstAudit.getByRole("button", { name: "Комментарий" }).click();
  await firstAudit
    .getByLabel("Комментарий")
    .fill("Проверено при внешней приёмке пилотного контура");
  await firstAudit
    .getByRole("button", { name: "Сохранить комментарий" })
    .click();
  await expect(firstAudit.getByText("Добавлен комментарий")).toBeVisible();
  await firstAudit
    .getByRole("link", { name: /Исходный фрагмент/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Точное место в исходном документе" }),
  ).toBeVisible();
  await page.goto(`/modes/tender/workspaces/${workspaceId}/result`);
  await page
    .locator(".export-card")
    .filter({ hasText: "Протокол разногласий" })
    .getByRole("button", { name: "Подготовить DOCX" })
    .click();
  const protocol = page.waitForEvent("download");
  await page
    .getByRole("link", { name: /Скачать Протокол разногласий \(DOCX\)/ })
    .click();
  expect((await protocol).suggestedFilename()).toMatch(/\.docx$/);
  await page.getByRole("button", { name: "Подготовить общий архив" }).click();
  const resultArchive = page.waitForEvent("download");
  await page
    .getByRole("link", { name: /Скачать Архив результатов объекта \(ZIP\)/ })
    .click();
  expect((await resultArchive).suggestedFilename()).toMatch(/\.zip$/);

  await page.goto(`/modes/support/workspaces/${workspaceId}/support-id`);
  const sseOpened = await page.evaluate(async (eventsUrl) => {
    return await new Promise<boolean>((resolve) => {
      const source = new EventSource(eventsUrl);
      const timer = window.setTimeout(() => {
        source.close();
        resolve(false);
      }, 10_000);
      source.onopen = () => {
        window.clearTimeout(timer);
        source.close();
        resolve(true);
      };
      source.onerror = () => {
        window.clearTimeout(timer);
        source.close();
        resolve(false);
      };
    });
  }, `/api/v1/workspaces/${workspaceId}/events`);
  expect(sseOpened).toBe(true);
  for (const version of [1, 2, 3, 4]) {
    await expect(
      page.getByText(`Версия комплекта ${String(version)}`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`Версия реестра ${String(version)}`, { exact: true }),
    ).toBeVisible();
  }
  await expect(
    page.getByText("Финализирован", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Отсутствует").first()).toBeVisible();
  await expect(page.getByText("Заблокировано").first()).toBeVisible();
  const finalizedLink = page.getByRole("link", {
    name: "Скачать финализированный документ",
  });
  const href = await finalizedLink.getAttribute("href");
  if (!href) throw new Error("finalized document URL is missing");
  const full = await page.request.get(href);
  expect(full.status()).toBe(200);
  expect(full.headers()["content-type"]).toContain("application/pdf");
  const bytes = await full.body();
  expect(`sha256:${createHash("sha256").update(bytes).digest("hex")}`).toBe(
    expectedPdfDigest,
  );
  const range = await page.request.get(href, {
    headers: { Range: "bytes=0-31" },
  });
  expect(range.status()).toBe(206);
  expect((await range.body()).byteLength).toBe(32);
  expect(range.headers()["content-range"]).toMatch(/^bytes 0-31\//);

  await page.goto("/admin/system");
  await page.getByText("Технические сведения", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Развёртывание" }),
  ).toBeVisible();
  await expect(page.getByText("public-development-contour")).toBeVisible();

  await page.getByRole("button", { name: "Выйти" }).click();
  await expect(page.getByRole("heading", { name: "АСД-КОНТУР" })).toBeVisible();
  const afterLogout = await page.request.get("/api/v1/workspaces");
  expect(afterLogout.status()).toBe(401);
});

test("owner creates an object and completes the four-mode pilot path", async ({
  page,
}) => {
  test.skip(
    !corpusRoot,
    "ASD_PUBLIC_E2E_CORPUS_ROOT is required for the full pilot path",
  );
  test.setTimeout(360_000);
  const objectName =
    process.env.ASD_PUBLIC_E2E_PILOT_NAME ??
    "Квалификационный объект пробной эксплуатации";

  await page.goto("/login");
  await page.getByLabel("Пользователь").fill(username);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await page
    .getByRole("link", { name: "Тендерный анализ", exact: true })
    .click();
  await page.getByLabel("Название объекта").fill(objectName);
  await page.getByRole("button", { name: "Создать объект" }).click();
  await expect(page).toHaveURL(/\/modes\/tender\/workspaces\/[^/]+$/);
  const workspaceMatch = page.url().match(/\/workspaces\/([^/]+)$/);
  const workspaceId = workspaceMatch?.[1];
  if (!workspaceId) throw new Error("created workspace identity is missing");

  await page.getByRole("link", { name: "Документы", exact: true }).click();
  await page
    .getByLabel("Выбрать файлы")
    .setInputFiles(corpusPaths(corpusRoot as string));
  await expect(page.getByText("13 файлов")).toBeVisible();
  await page.getByRole("button", { name: "Начать загрузку" }).click();
  await expect(page.getByText(/Принято новых файлов: 14/)).toBeVisible();
  await expect(page.getByText(/Не поддержано или отклонено: 1/)).toBeVisible();
  await waitForWorkspaceJobs(page, workspaceId);

  await page.goto(
    `/modes/tender/workspaces/${workspaceId}/project-understanding`,
  );
  await page
    .getByRole("button", { name: "Сформировать модель объекта" })
    .click();
  await waitForWorkspaceJobs(page, workspaceId);
  await expect
    .poll(
      async () =>
        page.evaluate(
          async (identity) =>
            (
              await fetch(
                `/api/v1/workspaces/${identity}/project-understanding`,
              )
            ).status,
          workspaceId,
        ),
      { timeout: 60_000 },
    )
    .toBe(200);
  await page.reload();
  await expect(
    page.getByText("Учебно-производственный корпус").first(),
  ).toBeVisible();

  const firstCandidate = page
    .locator(".candidate-row")
    .filter({ hasText: "Учебно-производственный корпус" });
  await firstCandidate.getByRole("button", { name: "Подтвердить" }).click();
  await expect(firstCandidate.getByText("Подтверждено")).toBeVisible();
  const levelsCandidate = page
    .locator(".candidate-row")
    .filter({ hasText: "0,000; +4,200" });
  await levelsCandidate.getByRole("button", { name: "Исправить" }).click();
  await levelsCandidate
    .getByLabel("Исправленное значение")
    .fill("0.000; +4.200");
  await levelsCandidate
    .getByLabel("Причина изменения")
    .fill("Приведён формат десятичного разделителя без изменения отметок");
  await levelsCandidate
    .getByRole("button", { name: "Сохранить новую версию" })
    .click();
  await expect(levelsCandidate.getByText("Исправлено")).toBeVisible();

  const outputs = [
    ["tender", "Тендерный анализ", "Протокол разногласий"],
    ["support", "Инженерное сопровождение", "Матрица работ и требований"],
    ["audit", "Аудит", "Отчёт аудита"],
    ["restoration", "Восстановление", "План восстановления"],
  ] as const;
  for (const [mode, title, output] of outputs) {
    await page.goto(`/modes/${mode}/workspaces/${workspaceId}/result`);
    const form = page.getByRole("button", { name: "Сформировать результат" });
    const outputHeading = page.getByText(output, { exact: true });
    await expect(form.or(outputHeading)).toBeVisible();
    if (await form.isVisible()) await form.click();
    await expect(
      page.getByRole("heading", { name: `Результат: ${title}` }),
    ).toBeVisible();
    await expect(outputHeading).toBeVisible();
  }

  await createAndDownload(
    page,
    workspaceId,
    "tender",
    "Протокол разногласий",
    "DOCX",
  );
  await createAndDownload(
    page,
    workspaceId,
    "tender",
    "Предлагаемые изменения к договору",
    "PDF",
  );
  await createAndDownload(
    page,
    workspaceId,
    "support",
    "Матрица работ и требований",
    "DOCX",
  );
  await createAndDownload(
    page,
    workspaceId,
    "support",
    "Комплект исполнительной документации",
    "ZIP",
  );
  await createAndDownload(
    page,
    workspaceId,
    "support",
    "Реестр документов комплекта",
    "PDF",
  );
  await createAndDownload(page, workspaceId, "audit", "Отчёт аудита", "PDF");
  await createAndDownload(
    page,
    workspaceId,
    "restoration",
    "План восстановления",
    "DOCX",
  );
  await createAndDownload(
    page,
    workspaceId,
    "restoration",
    "Проекты восстанавливаемых документов",
    "ZIP",
  );
  await page.goto(`/modes/tender/workspaces/${workspaceId}/result`);
  await page
    .getByRole("link", { name: /Исходный фрагмент/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Точное место в исходном документе" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/modes/tender/workspaces/${workspaceId}/result`);
  expect(
    await page.evaluate(
      () =>
        globalThis.document.documentElement.scrollWidth ===
        globalThis.document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole("button", { name: "Подготовить общий архив" }).click();
  const archive = page.waitForEvent("download");
  await page
    .getByRole("link", { name: /Скачать Архив результатов объекта \(ZIP\)/ })
    .click();
  expect((await archive).suggestedFilename()).toMatch(/\.zip$/);

  await page.getByRole("button", { name: "Выйти" }).click();
  await page.getByLabel("Пользователь").fill(username);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
  await page.goto(`/modes/audit/workspaces/${workspaceId}/result`);
  await expect(
    page.getByRole("heading", { name: "Результат: Аудит" }),
  ).toBeVisible();
  await expect(page.getByText("Отчёт аудита", { exact: true })).toBeVisible();
});

async function waitForWorkspaceJobs(
  page: import("@playwright/test").Page,
  workspaceId: string,
) {
  await expect
    .poll(
      async () =>
        page.evaluate(async (identity) => {
          const response = await fetch(`/api/v1/workspaces/${identity}/jobs`);
          if (!response.ok) return -1;
          const jobs = (await response.json()) as Array<{ state: string }>;
          return jobs.filter((job) =>
            ["queued", "leased", "running", "paused"].includes(job.state),
          ).length;
        }, workspaceId),
      { timeout: 300_000, intervals: [1_000, 2_000, 5_000] },
    )
    .toBe(0);
}

async function createAndDownload(
  page: import("@playwright/test").Page,
  workspaceId: string,
  mode: string,
  title: string,
  format: "DOCX" | "PDF" | "ZIP",
) {
  await page.goto(`/modes/${mode}/workspaces/${workspaceId}/result`);
  const card = page.locator(".export-card").filter({ hasText: title });
  await card
    .getByRole("button", {
      name: format === "ZIP" ? "Подготовить архив" : `Подготовить ${format}`,
    })
    .click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("link", { name: new RegExp(`Скачать ${title} \\(${format}\\)`) })
    .click();
  expect((await download).suggestedFilename()).toMatch(
    new RegExp(`\\.${format.toLowerCase()}$`),
  );
}

function corpusPaths(root: string): string[] {
  const paths: string[] = [];
  const visit = (directory: string) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.name !== "corpus-manifest.json") paths.push(path);
    }
  };
  visit(root);
  return paths.sort();
}
