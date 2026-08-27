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
      name: "Доказательная работа со строительной документацией",
    }),
  ).toBeVisible();
  const content = await page.locator("body").innerText();
  for (const forbidden of ["ИСУИД", "24 337", "24337", "690 томов"])
    expect(content).not.toContain(forbidden);
  await expect(
    page.getByRole("link", { name: "Войти в АСД-КОНТУР" }).first(),
  ).toHaveAttribute("href", "https://app.asd-kontur.ru");
});

test("authenticated Product Spine exposes finalized synthetic package evidence", async ({
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
    page.getByRole("heading", { name: "Рабочие пространства" }),
  ).toBeVisible();
  const workspace = page
    .locator("article")
    .filter({ hasText: "Synthetic" })
    .first();
  const target = await workspace
    .getByRole("link", { name: "Открыть" })
    .getAttribute("href");
  if (!target) throw new Error("synthetic workspace link is missing");
  const workspaceId = target.split("/").at(-1);
  if (!workspaceId) throw new Error("synthetic workspace identity is missing");

  for (const path of ["documents", "evidence", "work-matrix"]) {
    await page.goto(`/workspaces/${workspaceId}/${path}`);
    await expect(page.locator("main")).toBeVisible();
  }
  for (const mode of ["Tender", "Support", "Audit", "Restoration"]) {
    await page.goto(`/workspaces/${workspaceId}/modes/${mode}`);
    await expect(page.getByRole("heading", { name: mode })).toBeVisible();
  }

  await page.goto(`/workspaces/${workspaceId}/support-id`);
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
      page.getByText(`PackageVersion ${String(version)}`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`RegisterVersion ${String(version)}`, { exact: true }),
    ).toBeVisible();
  }
  await expect(
    page.getByText("finalized", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Missing").first()).toBeVisible();
  await expect(page.getByText("Blocked").first()).toBeVisible();
  const finalizedLink = page.getByRole("link", { name: "Скачать finalized" });
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

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "Deployment" })).toBeVisible();
  await expect(page.getByText("public-development-contour")).toBeVisible();
});
