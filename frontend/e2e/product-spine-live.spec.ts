import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, unlinkSync } from "node:fs";
import { resolve } from "node:path";

const repository = resolve(import.meta.dirname, "../..");
const statePath = process.env.ASD_E2E_STATE_PATH;

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
    page.getByRole("heading", { name: "Рабочие пространства" }),
  ).toBeVisible();
  await page.goto(`/workspaces/${state.support_workspace_id}/support-id`);
  await expect(
    page.getByRole("heading", {
      name: "Support / Исполнительная документация",
    }),
  ).toBeVisible();
  await expect(
    page.getByText("support.aosr", { exact: true }).first(),
  ).toBeVisible();
  const register = page.locator("tbody tr").filter({ hasText: "register" });
  await expect(register.locator("td").first()).toHaveText("1");
  await expect(
    page.getByText("finalized", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/template .* · active/)).toBeVisible();
  await expect(page.getByText("print: print_ready")).toBeVisible();
  await expect(page.getByText("review: approved")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Immutable package / register history" }),
  ).toBeVisible();
  for (const version of [1, 2, 3, 4]) {
    await expect(
      page.getByText(`PackageVersion ${String(version)}`, { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(`RegisterVersion ${String(version)}`, { exact: true }),
    ).toBeVisible();
  }
  await expect(page.getByText("Finalized").first()).toBeVisible();
  await expect(page.getByText("1", { exact: true }).first()).toBeVisible();
  await expect(
    page.getByText("work_type.classification").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "exact evidence" }).first(),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Скачать finalized" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
});

test("live PostgreSQL spine survives worker loss and isolated reset", async ({
  page,
}) => {
  if (!statePath) throw new Error("ASD_E2E_STATE_PATH is required");
  const marker = `/tmp/asd-kontur-spine-worker-${String(process.pid)}.marker`;
  let interrupted: ChildProcess | null = null;
  try {
    await page.goto("/login");
    await page.getByLabel("Пользователь").fill("synthetic-live-owner");
    await page.getByLabel("Пароль").fill("Synthetic-Live-Owner-Password-42!");
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page.getByText("Workspace ещё не созданы.")).toBeVisible();

    await page.getByLabel("Название workspace").fill("Live workspace A");
    await page.getByRole("button", { name: "Создать" }).click();
    const workspaceACard = page.locator("article").filter({
      has: page.getByRole("heading", { name: "Live workspace A" }),
    });
    const workspaceAPath = await workspaceACard
      .getByRole("link", { name: "Открыть" })
      .getAttribute("href");
    if (!workspaceAPath) throw new Error("workspace A link missing");
    const workspaceA = workspaceAPath.split("/").at(-1);
    if (!workspaceA) throw new Error("workspace A identity missing");
    await workspaceACard.getByRole("link", { name: "Открыть" }).click();
    await page.getByRole("link", { name: "Documents" }).click();
    await page.getByLabel("Добавить файлы").setInputFiles([
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
    await page.getByRole("link", { name: "Jobs", exact: true }).click();
    await expect(page.getByText("running")).toBeVisible();
    await page.waitForTimeout(5_500);
    const restarted = worker("drain", undefined, 27);
    expect(await exited(restarted)).toBe(0);
    await expect
      .poll(
        async () =>
          page.locator("tbody tr").filter({ hasText: "succeeded" }).count(),
        { timeout: 15_000 },
      )
      .toBe(26);

    await page.getByRole("link", { name: "Documents" }).click();
    await expect(
      page.getByRole("link", { name: "live-two-pages.pdf" }),
    ).toHaveCount(1);
    await page.getByRole("link", { name: "live-two-pages.pdf" }).click();
    await expect(page.getByLabel("PDF page 1")).toBeVisible();
    await expect(page.getByLabel("Evidence locator region")).toBeVisible();
    await expect(
      page.getByText("NO_VERIFIED_FACT_BOUND_TO_LOCATOR"),
    ).toBeVisible();
    await expect(page.getByText("none", { exact: true })).toBeVisible();

    await page
      .getByRole("link", { name: "Project Understanding", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Project Understanding" }),
    ).toBeVisible();
    await expect(page.getByText("Устройство монолитной плиты")).toBeVisible();
    await page.locator("article.entity-card a").first().click();
    await expect(
      page.getByRole("heading", { name: "Exact Evidence Locator" }),
    ).toBeVisible();
    await expect(page.getByText("workspace_fact_candidate")).toBeVisible();

    for (const mode of ["Tender", "Support", "Audit", "Restoration"]) {
      await page.getByRole("link", { name: mode, exact: true }).click();
      await expect(page.getByRole("heading", { name: mode })).toBeVisible();
      await expect(page.getByText("PARTIAL", { exact: true })).toBeVisible();
    }
    await page.getByRole("link", { name: "Platform Knowledge" }).click();
    await expect(
      page.getByRole("heading", { name: "KnowledgeReady = false" }),
    ).toBeVisible();
    await expect(page.getByText("MEMORY_DATA_DEFECT").last()).toBeVisible();
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

    await page.getByRole("link", { name: "Workspaces" }).click();
    await page.getByLabel("Название workspace").fill("Live workspace B");
    await page.getByRole("button", { name: "Создать" }).click();
    await expect(page.getByText("Live workspace B")).toBeVisible();
    await page.goto(`/workspaces/${workspaceA}`);
    await page.getByRole("button", { name: "Подготовить reset" }).click();
    const confirmation = await page.locator(".danger-text code").textContent();
    if (!confirmation) throw new Error("reset confirmation missing");
    await page.getByLabel("Подтверждение exact target").fill(confirmation);
    await page.getByRole("button", { name: "Выполнить reset" }).click();
    await expect(page.getByText("Live workspace B")).toBeVisible();
    await expect(page.getByText("Live workspace A")).toHaveCount(0);
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
