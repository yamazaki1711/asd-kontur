export type PendingConstructionConsultantQuestion = {
  conversationId: string;
  question: string;
  requestId: string;
};

/**
 * Reuse a request identity only for the same persisted conversation and
 * unchanged question. This lets a user retry an interrupted submission without
 * turning an uncertain response into a second conversation message.
 */
export function constructionConsultantRequestId(
  pending: PendingConstructionConsultantQuestion | null,
  conversationId: string,
  question: string,
  createRequestId: () => string,
): string {
  if (
    pending?.conversationId === conversationId &&
    pending.question === question
  ) {
    return pending.requestId;
  }
  return createRequestId();
}
