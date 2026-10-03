import { describe, expect, it } from "vitest";

import { mergeFieldResolutionRows } from "./supportFieldRows";

describe("mergeFieldResolutionRows", () => {
  it("keeps one unresolved field and every distinct source locator", () => {
    const rows = mergeFieldResolutionRows([
      {
        generation_run_id: "run-1",
        field_key: "work_description",
        state: "confirmed",
        normalized_value: "concrete_work",
        fact_id: "fact-1",
        fact_version: 1,
        source_locator_id: "locator-b",
      },
      {
        generation_run_id: "run-1",
        field_key: "work_description",
        state: "confirmed",
        normalized_value: "concrete_work",
        fact_id: "fact-1",
        fact_version: 1,
        source_locator_id: "locator-a",
      },
      {
        generation_run_id: "run-1",
        field_key: "as_built_level",
        state: "missing",
        normalized_value: null,
        fact_id: null,
        fact_version: null,
      },
    ]);

    expect(rows).toHaveLength(2);
    expect(rows.map((row) => row.field.field_key)).toEqual([
      "as_built_level",
      "work_description",
    ]);
    expect(rows[0]?.locatorIds).toEqual([]);
    expect(rows[1]?.locatorIds).toEqual(["locator-a", "locator-b"]);
  });
});
