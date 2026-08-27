import { defineConfig } from "@playwright/test";

const baseURL = process.env.ASD_PUBLIC_E2E_APP_URL;
if (!baseURL) throw new Error("ASD_PUBLIC_E2E_APP_URL is required");

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
