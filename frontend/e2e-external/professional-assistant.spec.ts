import { expect, test, type Page } from "@playwright/test";

const username = process.env.ASD_PUBLIC_E2E_USERNAME;
const password = process.env.ASD_PUBLIC_E2E_PASSWORD;
const workspaceName =
  process.env.ASD_PUBLIC_E2E_WORKSPACE_NAME ??
  "Квалификационный объект пробной эксплуатации 06";

if (!username) throw new Error("ASD_PUBLIC_E2E_USERNAME is required");
if (!password) throw new Error("ASD_PUBLIC_E2E_PASSWORD is required");

test("local Qwen assistant serves all four modes with scoped exact sources", async ({
  page,
}) => {
  test.setTimeout(900_000);
  await login(page);
  await page
    .getByRole("link", { name: "Инженерное сопровождение", exact: true })
    .click();
  const workspace = page
    .locator("article")
    .filter({ hasText: workspaceName })
    .first();
  const target = await workspace
    .getByRole("link", { name: "Открыть" })
    .getAttribute("href");
  if (!target) throw new Error("qualified pilot workspace link is missing");
  const workspaceId = target.split("/").at(-1);
  if (!workspaceId)
    throw new Error("qualified pilot workspace identity is missing");

  const general = await ask(
    page,
    `/modes/support/workspaces/${workspaceId}`,
    "Как оформляется АОСР и какие документы обычно входят в соответствующий комплект исполнительной документации?",
  );
  expect(general.text).toMatch(/АОСР|акт освидетельствования/i);
  expect(general.text).toMatch(/пособ|методичес/i);
  const practiceLink = page
    .locator(".assistant-sources a")
    .filter({ hasText: /Пособие/ })
    .first();
  const normativeLink = page
    .locator(".assistant-sources a")
    .filter({ hasText: /СП \d/ })
    .first();
  await expect(practiceLink).toHaveAttribute("href", /#page=\d+/);
  await expect(normativeLink).toHaveAttribute("href", /#page=\d+/);
  for (const sourceLink of [practiceLink, normativeLink]) {
    const href = await sourceLink.getAttribute("href");
    if (!href) throw new Error("exact assistant source href is missing");
    const source = await page.request.get(href, {
      headers: { Range: "bytes=0-31" },
    });
    expect(source.status()).toBe(206);
    expect((await source.body()).byteLength).toBe(32);
  }
  await expect(
    page.getByText("Актуальность редакции не проверена").first(),
  ).toBeVisible();

  const currentObject = await ask(
    page,
    `/modes/support/workspaces/${workspaceId}`,
    "Какие виды работ обнаружены в этом объекте и по каким из них не хватает документов?",
  );
  expect(currentObject.text).toMatch(/монолит|гидроизоляц|трубопровод/i);

  const tender = await ask(
    page,
    `/modes/tender/workspaces/${workspaceId}`,
    "Какие расхождения между ведомостью объёмов и сметой создают риск для подрядчика?",
  );
  expect(tender.text).toMatch(/расхожд|объ[её]м|смет/i);

  const support = await ask(
    page,
    `/modes/support/workspaces/${workspaceId}`,
    "Что необходимо подготовить по выбранному виду работ для предъявления выполненных работ?",
  );
  expect(support.text).toMatch(/документ|контрол|АОСР|комплект/i);

  const audit = await ask(
    page,
    `/modes/audit/workspaces/${workspaceId}`,
    "Какие нарушения и пробелы обнаружены в документах объекта?",
  );
  expect(audit.text).toMatch(/пробел|отсутств|уточнен|расхожд/i);

  const restoration = await ask(
    page,
    `/modes/restoration/workspaces/${workspaceId}`,
    "Какие отсутствующие документы можно восстановить, а какие нельзя сформировать без дополнительных исходных данных?",
  );
  expect(restoration.text).toMatch(/восстанов|недостат|нельзя|исходн/i);

  const gap = await ask(
    page,
    `/modes/audit/workspaces/${workspaceId}`,
    "Каков серийный номер отсутствующего лабораторного прибора и кто подписал его поверку?",
  );
  expect(gap.text).toMatch(
    /нет сведений|недостаточно|не найден|требуется уточнить|отсутствуют сведения/i,
  );
  for (const result of [
    general,
    currentObject,
    tender,
    support,
    audit,
    restoration,
    gap,
  ]) {
    expect(result.text).not.toMatch(
      /Evidence Pack|RuleCandidate|SourceVersion|tool-call|reasoning/i,
    );
  }

  await page.reload();
  if (!(await page.getByTestId("assistant-panel").isVisible())) {
    await page.getByRole("button", { name: "Инженерный помощник" }).click();
  }
  await expect(page.getByText(gap.text, { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("assistant-panel")).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth ===
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.goto("/modes/support/workspaces");
  const isolatedName = `Проверка изоляции помощника ${String(Date.now())}`;
  await page.getByLabel("Название объекта").fill(isolatedName);
  await page.getByRole("button", { name: "Создать объект" }).click();
  await expect(page).toHaveURL(/\/modes\/support\/workspaces\/[^/]+$/);
  const isolatedMatch = page.url().match(/\/workspaces\/([^/]+)$/);
  const isolatedWorkspaceId = isolatedMatch?.[1];
  if (!isolatedWorkspaceId)
    throw new Error("isolated workspace identity is missing");
  const isolated = await ask(
    page,
    `/modes/support/workspaces/${isolatedWorkspaceId}`,
    "Какие виды работ и документы обнаружены в этом объекте?",
  );
  expect(isolated.text).toMatch(
    /нет сведений|недостаточно|не загруж|не обнаруж/i,
  );
  expect(isolated.text).not.toMatch(/монолит|гидроизоляц|трубопровод/i);
  await resetWorkspace(page, isolatedWorkspaceId);
});

test("an interrupted local inference has a durable visible outcome", async ({
  page,
}) => {
  test.skip(
    process.env.ASD_ASSISTANT_RESTART_E2E !== "1",
    "ASD_ASSISTANT_RESTART_E2E=1 is required for the controlled restart check",
  );
  test.setTimeout(240_000);
  await login(page);
  await page
    .getByRole("link", { name: "Инженерное сопровождение", exact: true })
    .click();
  const workspace = page
    .locator("article")
    .filter({ hasText: workspaceName })
    .first();
  const target = await workspace
    .getByRole("link", { name: "Открыть" })
    .getAttribute("href");
  if (!target) throw new Error("restart workspace link is missing");
  await page.goto(target);
  await page.getByRole("button", { name: "Инженерный помощник" }).click();
  const panel = page.getByTestId("assistant-panel");
  await panel.getByRole("button", { name: "Новый диалог" }).click();
  const question =
    "Подробно объясни порядок оформления АОСР, состав приложений и ограничения " +
    `для текущего объекта. Проверка ${String(Date.now())}`;
  await panel.getByLabel("Ваш вопрос").fill(question);
  await panel.getByRole("button", { name: "Отправить" }).click();
  await expect(panel.getByRole("button", { name: "Остановить" })).toBeVisible();
  console.log("ASSISTANT_RESTART_TURN_RUNNING");
  await expect(
    panel.getByText(
      "Помощник временно недоступен. Повторите вопрос после восстановления сервиса.",
    ),
  ).toBeVisible({ timeout: 180_000 });
  await page.reload();
  if (!(await page.getByTestId("assistant-panel").isVisible())) {
    await page.getByRole("button", { name: "Инженерный помощник" }).click();
  }
  await expect(
    page
      .getByTestId("assistant-panel")
      .locator(".assistant-message-question .assistant-answer")
      .filter({ hasText: question }),
  ).toBeVisible();
});

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Пользователь").fill(username as string);
  await page.getByLabel("Пароль").fill(password as string);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();
}

async function ask(page: Page, route: string, question: string) {
  await page.goto(route);
  const panel = page.getByTestId("assistant-panel");
  if (!(await panel.isVisible())) {
    await page.getByRole("button", { name: "Инженерный помощник" }).click();
  }
  await expect(panel).toBeVisible();
  const conversation = panel.getByLabel("Диалог");
  await panel.getByRole("button", { name: "Новый диалог" }).click();
  await expect(conversation).toHaveValue("");
  await panel.getByLabel("Ваш вопрос").fill(question);
  const startedAt = Date.now();
  await panel.getByRole("button", { name: "Отправить" }).click();
  const streamed = panel
    .locator(".assistant-message-answer .assistant-answer")
    .filter({ hasNotText: "Подбираю сведения и источники…" })
    .last();
  await expect(streamed).not.toHaveText("", { timeout: 180_000 });
  const firstVisibleMilliseconds = Date.now() - startedAt;
  await expect(
    panel.getByRole("button", { name: "Остановить" }),
  ).not.toBeVisible({
    timeout: 240_000,
  });
  const answer = panel
    .locator(".assistant-message-answer .assistant-answer")
    .last();
  const text = (await answer.innerText()).trim();
  await expect(panel.locator(".assistant-sources a").first()).toBeVisible();
  const totalMilliseconds = Date.now() - startedAt;
  console.log(
    JSON.stringify({ question, firstVisibleMilliseconds, totalMilliseconds }),
  );
  return { text, firstVisibleMilliseconds, totalMilliseconds };
}

async function resetWorkspace(page: Page, workspaceId: string) {
  const prepared = await page.evaluate(async (identity) => {
    const csrf = document.cookie
      .split("; ")
      .find((item) => item.startsWith("asd_csrf="))
      ?.split("=")[1];
    const response = await fetch(
      `/api/v1/workspaces/${identity}/lifecycle/reset/prepare`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf ?? "",
        },
        body: JSON.stringify({ confirmation: "PREPARE_WORKSPACE_RESET" }),
      },
    );
    return (await response.json()) as {
      challenge_id: string;
      confirmation_text: string;
    };
  }, workspaceId);
  await page.evaluate(
    async ({ identity, challenge }) => {
      const csrf = document.cookie
        .split("; ")
        .find((item) => item.startsWith("asd_csrf="))
        ?.split("=")[1];
      const response = await fetch(
        `/api/v1/workspaces/${identity}/lifecycle/reset/execute`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf ?? "",
          },
          body: JSON.stringify({
            challenge_id: challenge.challenge_id,
            confirmation_text: challenge.confirmation_text,
          }),
        },
      );
      if (!response.ok)
        throw new Error(`workspace reset failed: ${String(response.status)}`);
    },
    { identity: workspaceId, challenge: prepared },
  );
}
