export type SupportFieldResolutionRow = {
  field: Record<string, unknown>;
  locatorIds: string[];
};

export function mergeFieldResolutionRows(
  fields: Record<string, unknown>[],
): SupportFieldResolutionRow[] {
  const rows = new Map<
    string,
    { field: Record<string, unknown>; locatorIds: Set<string> }
  >();
  for (const field of fields) {
    const key = [
      field.generation_run_id,
      field.field_key,
      field.state,
      field.normalized_value,
      field.fact_id,
      field.fact_version,
    ]
      .map(fieldResolutionKeyText)
      .join(":");
    const row = rows.get(key) ?? { field, locatorIds: new Set<string>() };
    if (typeof field.source_locator_id === "string") {
      row.locatorIds.add(field.source_locator_id);
    }
    rows.set(key, row);
  }
  return Array.from(rows.values())
    .map((row) => ({ ...row, locatorIds: Array.from(row.locatorIds).sort() }))
    .sort((left, right) =>
      fieldResolutionKeyText(left.field.field_key).localeCompare(
        fieldResolutionKeyText(right.field.field_key),
      ),
    );
}

function fieldResolutionKeyText(value: unknown): string {
  return typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
    ? String(value)
    : "";
}
