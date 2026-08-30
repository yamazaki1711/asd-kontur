import { defineConfig } from "@playwright/test";

const e2eStatePath = "/tmp/asd-kontur-spine-e2e-state.json";
process.env.ASD_E2E_STATE_PATH = e2eStatePath;
process.env.ASD_E2E_PORT = "4173";
process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";
const webServerEnvironment = Object.fromEntries(
  Object.entries(process.env).filter(
    (entry): entry is [string, string] => entry[1] !== undefined,
  ),
);

export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      "npm run build && cd .. && uv run python tools/run_product_spine_e2e_server.py",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 180_000,
    env: webServerEnvironment,
  },
});
