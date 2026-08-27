import { expect, test } from "@playwright/test";

test("live NTD canaries expose native and raster version-pinned evidence", async ({
  page,
}) => {
  test.skip(
    process.env.ASD_E2E_EXPECT_NTD_NATIVE_CANARY !== "1",
    "requires a disposable clone of the qualified NTD recovery database",
  );
  await page.goto("/login");
  await page.getByLabel("Пользователь").fill("synthetic-live-owner");
  await page.getByLabel("Пароль").fill("Synthetic-Live-Owner-Password-42!");
  await page.getByRole("button", { name: "Войти" }).click();
  await page.getByRole("link", { name: "Platform Knowledge" }).click();

  await expect(
    page.getByRole("heading", { name: "KnowledgeReady = false" }),
  ).toBeVisible();
  await expect(
    page.locator(".metric").filter({ hasText: "Denominator" }),
  ).toContainText("25");
  const normativeRow = page.locator("tbody tr").filter({
    hasText: "СП 543.1325800.2024",
  });
  await expect(normativeRow).toContainText("534 verified provisions");
  await expect(normativeRow).toContainText("1 Practice↔NTD");
  await expect(normativeRow).toContainText("Practice↔NTD alignment");
  await expect(normativeRow).toContainText("edition_warning");
  await expect(normativeRow).toContainText("1 qualified rules");
  await expect(normativeRow).toContainText("7.1.13 · page 23");
  await expect(normativeRow).toContainText("edition: not_activated");
  await expect(normativeRow).toContainText("qualified → not_activated");
  await expect(normativeRow).toContainText("NORMATIVE_EDITION_NOT_ACTIVATED");
  await expect(normativeRow).toContainText("lifecycle: candidate");
  await normativeRow.getByText("7.1.13 · page 23", { exact: true }).click();
  await expect(
    normativeRow.getByRole("link", { name: /Evidence 1: page 23 region/ }),
  ).toHaveAttribute("href", /#page=23$/);

  if (process.env.ASD_E2E_SEED_ACTIVE_RULE === "1") {
    const activeRuleRow = page.locator("tbody tr").filter({
      hasText: "СП 347.1325800.2017",
    });
    await activeRuleRow.getByText("10.8 · page 40", { exact: true }).click();
    await expect(activeRuleRow).toContainText("qualified → active");
    await expect(activeRuleRow).toContainText(
      "QUALIFIED_RULE_AND_EDITION_ACTIVE",
    );
    await expect(activeRuleRow).toContainText("lifecycle: active");
    await expect(
      activeRuleRow.getByRole("link", { name: /Evidence 1: page 40 region/ }),
    ).toHaveAttribute("href", /#page=40$/);
  }

  const rasterRow = page.locator("tbody tr").filter({
    hasText: "СП 71.13330.2017",
  });
  await expect(rasterRow).toContainText("1 verified provisions");
  await expect(rasterRow).toContainText("external/page:1/clause:1 · page 1");
  await expect(rasterRow).toContainText("edition: not_activated");
  await rasterRow
    .getByText("external/page:1/clause:1 · page 1", { exact: true })
    .click();
  await expect(
    rasterRow.getByRole("link", { name: /Evidence 1: page 1 region/ }),
  ).toHaveAttribute("href", /#page=1$/);
});
