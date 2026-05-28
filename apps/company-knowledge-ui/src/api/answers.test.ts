import { afterEach, describe, expect, it, vi } from "vitest";

import { submitTopicQuestion } from "./answers";

describe("answer API", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends topic id, conversation id, and detailed answer depth", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "Answer",
        citations: []
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    await submitTopicQuestion({
      topic_id: "project-deployment",
      conversation_id: "conv-1",
      answer_depth: "detailed",
      question: "How do I deploy?"
    });

    const requestBody = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(requestBody).toMatchObject({
      topic_id: "project-deployment",
      conversation_id: "conv-1",
      answer_depth: "detailed",
      question: "How do I deploy?"
    });
  });
});
