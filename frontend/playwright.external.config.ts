import { defineConfig } from "@playwright/test";

const baseURL = process.env.ASD_PUBLIC_E2E_APP_URL;
if (!baseURL) throw new Error("ASD_PUBLIC_E2E_APP_URL is required");
// The external suite observes the owner's application. It is never a fixture
// target: synthetic project admission belongs to the disposable local E2E
// database and object store configured by playwright.config.ts.
if (process.env.ASD_PUBLIC_E2E_CORPUS_ROOT) {
  throw new Error(
    "External E2E cannot admit a control corpus into the live application; use the isolated E2E target",
  );
}

export default defineConfig({
  testDir: "./e2e-external",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  timeout: 60_000,
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
});
