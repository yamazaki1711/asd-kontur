import type { ReactNode } from "react";

export function StatusPill({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "warning" | "danger";
}) {
  return <span className={`status ${tone}`}>{children}</span>;
}
