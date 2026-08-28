import { createHash } from "node:crypto";

import { expect, test } from "@playwright/test";

const website = process.env.ASD_PUBLIC_E2E_WEBSITE_URL;
const username = process.env.ASD_PUBLIC_E2E_USERNAME;
const password = process.env.ASD_PUBLIC_E2E_PASSWORD;
const expectedPdfDigest = process.env.ASD_PUBLIC_E2E_PDF_DIGEST;

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
  await expect(page.getByRole("heading", { name: "Deployment" })).toBeVisible();
  await expect(page.getByText("public-development-contour")).toBeVisible();

  await page.getByRole("button", { name: "Выйти" }).click();
  await expect(page.getByRole("heading", { name: "АСД-КОНТУР" })).toBeVisible();
  const afterLogout = await page.request.get("/api/v1/workspaces");
  expect(afterLogout.status()).toBe(401);
});
