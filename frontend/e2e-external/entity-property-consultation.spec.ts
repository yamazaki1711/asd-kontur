import { expect, test } from "@playwright/test";

// Real-workspace qualification takes its identity from the operator, never
// from a project name or an expected answer embedded in product code.
const username = process.env.ASD_PUBLIC_E2E_USERNAME;
const password = process.env.ASD_PUBLIC_E2E_PASSWORD;
const workspaceId = process.env.ASD_PUBLIC_E2E_WORKSPACE_ID;

test("project consultant answers a pipe property question with source links", async ({
  page,
}) => {
  test.skip(
    !username || !password || !workspaceId,
    "Approved login and workspace ID are required for real-project qualification",
  );
  test.setTimeout(900_000);

  await page.goto("/login");
  await page.getByLabel("Пользователь").fill(username as string);
  await page.getByLabel("Пароль").fill(password as string);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(
    page.getByRole("heading", { name: "Выберите режим работы" }),
  ).toBeVisible();

  await page.goto(`/modes/tender/workspaces/${workspaceId as string}`);
  const launcher = page.getByRole("button", { name: "Инженерный помощник" });
  await expect(launcher).toBeVisible();
  await launcher.click();
  const panel = page.getByTestId("assistant-panel");
  await panel.getByRole("button", { name: "Новый диалог" }).click();
  await panel
    .getByLabel("Ваш вопрос")
    .fill(
      "Каковы диаметр и протяженность водоводной трубы, подлежащей демонтажу и замене новой трубой? Разделите существующую и новую трубы и укажите источники.",
    );
  await panel.getByRole("button", { name: "Отправить" }).click();
  await expect(panel.getByRole("button", { name: "Остановить" })).not.toBeVisible({
    timeout: 480_000,
  });

  const answer = panel.locator(".assistant-message-answer .assistant-answer").last();
  await expect(answer).toBeVisible();
  const text = (await answer.innerText()).trim();
  expect(text).not.toMatch(/Не могу надёжно опубликовать сформированный вывод/);
  expect(text).toMatch(/диаметр|∅|DN|Ду/i);
  expect(text).toMatch(/длин|протяж|м\b|км\b/i);
  await expect(panel.locator(".assistant-sources a").first()).toBeVisible();
});
