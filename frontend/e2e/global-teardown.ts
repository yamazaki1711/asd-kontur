import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

export default function globalTeardown() {
  const repository = resolve(import.meta.dirname, "../..");
  const outcome = spawnSync(
    "uv",
    ["run", "python", "tools/cleanup_product_spine_e2e.py"],
    { cwd: repository, env: process.env, encoding: "utf-8" },
  );
  if (outcome.status !== 0) {
    throw new Error(
      `live E2E cleanup failed: ${outcome.stderr || outcome.stdout}`,
    );
  }
}
