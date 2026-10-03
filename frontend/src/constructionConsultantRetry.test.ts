import { describe, expect, it } from "vitest";

import { constructionConsultantRequestId } from "./constructionConsultantRetry";

describe("constructionConsultantRequestId", () => {
  it("reuses an interrupted request only for the same conversation and text", () => {
    const pending = {
      conversationId: "conversation-a",
      question: "Как проверить материал?",
      requestId: "request-a",
    };

    expect(
      constructionConsultantRequestId(
        pending,
        "conversation-a",
        "Как проверить материал?",
        () => "new-request",
      ),
    ).toBe("request-a");
    expect(
      constructionConsultantRequestId(
        pending,
        "conversation-a",
        "Как оформить входной контроль?",
        () => "new-request",
      ),
    ).toBe("new-request");
    expect(
      constructionConsultantRequestId(
        pending,
        "conversation-b",
        "Как проверить материал?",
        () => "new-request",
      ),
    ).toBe("new-request");
  });
});
