import { afterEach, describe, expect, it, vi } from "vitest";

import { streamTopicQuestion, submitTopicQuestion } from "./answers";

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

  it("passes abort signals to streaming answer fetches", async () => {
    const controller = new AbortController();
    const response = new Response(
      'event: final\ndata: {"answer":"Stopped test","citations":[],"metadata":{"response_id":"resp-1"}}\n\n',
      { status: 200 }
    );
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);

    await streamTopicQuestion(
      {
        topic_id: "project-deployment",
        conversation_id: "conv-1",
        question: "How do I deploy?"
      },
      { onDelta: () => undefined },
      { signal: controller.signal }
    );

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });
});
