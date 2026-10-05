import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET, PATCH } from "./route";

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("API proxy route", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("BACKEND_INTERNAL_URL", "http://backend:8000/");
    vi.stubEnv("API_TOKEN", "s3cret");
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json", "content-encoding": "gzip", connection: "keep-alive" },
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    fetchMock.mockReset();
  });

  it("forwards to the backend with the server-side token", async () => {
    const req = new NextRequest("http://studio.local/api/v1/photos?page=2", {
      headers: { authorization: "Bearer attacker", "accept-encoding": "gzip" },
    });
    const res = await GET(req, ctx(["v1", "photos"]));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://backend:8000/api/v1/photos?page=2");
    const headers = init.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer s3cret");
    expect(headers.get("accept-encoding")).toBe("identity");
    expect(res.headers.get("content-encoding")).toBeNull();
    expect(res.headers.get("connection")).toBeNull();
  });

  it("rejects paths outside /api/v1 and traversal segments", async () => {
    const req = new NextRequest("http://studio.local/api/x");
    expect((await GET(req, ctx(["metrics"]))).status).toBe(404);
    expect((await GET(req, ctx(["v1", "..", "..", "etc"]))).status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("encodes segments so they cannot smuggle slashes", async () => {
    const req = new NextRequest("http://studio.local/api/v1/photos/a%2F..%2Fb");
    await GET(req, ctx(["v1", "photos", "a/../b"]));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://backend:8000/api/v1/photos/a%2F..%2Fb");
  });

  it("forwards request bodies", async () => {
    const req = new NextRequest("http://studio.local/api/v1/photos/abc", {
      method: "PATCH",
      body: JSON.stringify({ rating: 5 }),
      headers: { "content-type": "application/json" },
    });
    await PATCH(req, ctx(["v1", "photos", "abc"]));
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("PATCH");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"rating":5}');
  });

  it("returns 502 when the backend is down", async () => {
    fetchMock.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const res = await GET(new NextRequest("http://studio.local/api/v1/stats"), ctx(["v1", "stats"]));
    expect(res.status).toBe(502);
    expect((await res.json()).detail).toMatch(/backend unreachable/);
  });
});
