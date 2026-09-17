import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy to the Pulse backend REST API.
 *
 * This is the dashboard's entire authentication boundary. Pulse has a
 * single static API key today (see backend/docs/architecture.md) --
 * there is no per-user identity system. Embedding that key in
 * client-side code (even a NEXT_PUBLIC_ env var) would expose it to
 * anyone who opens browser devtools, since NEXT_PUBLIC_ variables are
 * bundled into the JS shipped to the browser.
 *
 * Instead: PULSE_API_KEY is a server-only environment variable (no
 * NEXT_PUBLIC_ prefix), read only here, on the Next.js server. The
 * browser calls this route (same-origin, no key needed), and this route
 * attaches the key when it forwards the request to the real backend.
 *
 * This is an honest, minimal boundary for a single-operator internal
 * tool -- it is NOT a multi-user auth system. Anyone who can reach this
 * Next.js server's HTTP port can use the dashboard. A production
 * deployment with multiple operators would need its own session/identity
 * layer in front of this proxy; that is a documented limitation, not
 * implemented speculatively (see README.md's Operations Dashboard
 * section).
 */

const BACKEND_URL = process.env.PULSE_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.PULSE_API_KEY ?? "";

async function forward(
  req: NextRequest,
  { params }: { params: { path: string[] } }
): Promise<NextResponse> {
  const path = params.path.join("/");
  const search = req.nextUrl.search;
  const url = `${BACKEND_URL}/api/v1/${path}${search}`;

  let body: string | undefined;
  if (!["GET", "HEAD"].includes(req.method)) {
    body = await req.text();
  }

  let backendResponse: Response;
  try {
    backendResponse = await fetch(url, {
      method: req.method,
      headers: {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    });
  } catch {
    // The backend is unreachable -- distinguished from a normal HTTP
    // error response so the UI can show an explicit "backend
    // unavailable" state rather than misreading this as "0 results."
    return NextResponse.json(
      {
        error: {
          code: "BACKEND_UNREACHABLE",
          message: "Could not reach the Pulse API.",
        },
      },
      { status: 503 }
    );
  }

  const responseBody = await backendResponse.text();
  return new NextResponse(responseBody, {
    status: backendResponse.status,
    headers: {
      "Content-Type": backendResponse.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export { forward as GET, forward as POST };
