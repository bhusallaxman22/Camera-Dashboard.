import type { NextRequest } from "next/server";

/**
 * Same-origin reverse proxy: browser -> Next.js -> backend container.
 *
 * - Keeps the backend URL and API token server-side (runtime env, not baked
 *   into the bundle), so the UI works unchanged on LAN or behind Cloudflare.
 * - Streams bodies both ways, so SSE and multi-GB NEF/video downloads work.
 */
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "accept-encoding",
  "content-encoding",
]);

function backendUrl(): string {
  return (process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await ctx.params;
  // Only the versioned API is exposed; segments are re-encoded so "..",
  // encoded slashes, etc. cannot escape the /api/ prefix on the backend.
  if (path[0] !== "v1" || path.some((s) => s === ".." || s === ".")) {
    return Response.json({ detail: "not found" }, { status: 404 });
  }
  const target = `${backendUrl()}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "authorization") headers.set(key, value);
  });
  // Upstream gzip would be transparently decoded by fetch, leaving a stale
  // content-encoding header; ask for identity instead.
  headers.set("accept-encoding", "identity");
  const token = process.env.API_TOKEN;
  if (token) headers.set("authorization", `Bearer ${token}`);

  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      signal: req.signal,
      // Never leak the internal backend hostname via a Location header.
      redirect: "follow",
      cache: "no-store",
    });
  } catch (err) {
    if (req.signal.aborted) return new Response(null, { status: 499 });
    const message = err instanceof Error ? err.message : String(err);
    return Response.json({ detail: `backend unreachable: ${message}` }, { status: 502 });
  }

  const resHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) resHeaders.set(key, value);
  });
  if (upstream.headers.get("content-type")?.startsWith("text/event-stream")) {
    resHeaders.set("cache-control", "no-cache, no-transform");
    resHeaders.set("x-accel-buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: resHeaders });
}

export {
  proxy as DELETE,
  proxy as GET,
  proxy as HEAD,
  proxy as OPTIONS,
  proxy as PATCH,
  proxy as POST,
  proxy as PUT,
};
