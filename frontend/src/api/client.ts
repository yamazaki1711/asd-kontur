import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: "",
  credentials: "include",
});

api.use({
  onRequest({ request }) {
    if (!new Set(["GET", "HEAD", "OPTIONS"]).has(request.method)) {
      const csrf = document.cookie
        .split("; ")
        .find((value) => value.startsWith("asd_csrf="))
        ?.split("=")[1];
      if (csrf) request.headers.set("X-CSRF-Token", decodeURIComponent(csrf));
    }
    return request;
  },
});

export function requireData<T>(value: T | undefined, error: unknown): T {
  if (value !== undefined) return value;
  if (typeof error === "object" && error !== null && "error" in error) {
    const envelope = error as { error?: { code?: string } };
    throw new Error(envelope.error?.code ?? "api_request_failed");
  }
  throw new Error("api_request_failed");
}
