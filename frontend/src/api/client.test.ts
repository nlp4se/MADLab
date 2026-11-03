import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getApiBaseUrl, request } from "./client";

describe("getApiBaseUrl", () => {
  it("falls back to the localhost /api default and strips trailing slashes", () => {
    // VITE_API_BASE_URL is unset in the test env, so the default applies.
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api");
  });
});

describe("request", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses a JSON body on success", async () => {
    const payload = { ok: true, value: 42 };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const result = await request<typeof payload>("/taxonomy");
    expect(result).toEqual(payload);
  });

  it("raises an ApiError carrying the backend error message on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "nope" }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    await expect(request("/configs")).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "nope",
    });
  });

  it("builds query strings and skips undefined params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("null", {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await request("/datasets", {
      query: { row_index: 2, skip: undefined, preview: true },
    });

    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toContain("row_index=2");
    expect(calledUrl).toContain("preview=true");
    expect(calledUrl).not.toContain("skip");
  });
});

describe("ApiError", () => {
  it("retains status and payload", () => {
    const err = new ApiError(500, "boom", { detail: "boom" });
    expect(err.status).toBe(500);
    expect(err.payload).toEqual({ detail: "boom" });
  });
});
