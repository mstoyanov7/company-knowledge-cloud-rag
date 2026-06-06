import { afterEach, describe, expect, it, vi } from "vitest";

import { register } from "./auth";

describe("auth API", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("treats registration as an access request without a session token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        email: "alex@example.com",
        status: "pending",
        message: "Your request is pending administrator approval."
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await register({
      email: "alex@example.com",
      password: "password-123",
      name: "Alex Morgan"
    });

    expect(response.status).toBe("pending");
    expect(response).not.toHaveProperty("access_token");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/auth/register");
  });
});
