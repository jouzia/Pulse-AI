import type {
  DeadLetterListResponse,
  DeadLetterRetryResponse,
  EventListResponse,
  EventResponse,
  JobDetailResponse,
  OpsOverviewResponse,
} from "./types";

/**
 * Result wrapper distinguishing three states the UI must render
 * differently (see Phase 5 spec's Step 17 and components/StateBlock.tsx):
 *   - ok: real data from the backend
 *   - unavailable: the backend/proxy could not be reached at all
 *   - error: the backend responded, but with an error (4xx/5xx)
 * None of these collapse into "0" or a default value -- that would be
 * exactly the misleading-observability failure mode Step 17 warns about.
 */
export type ApiResult<T> =
  | { kind: "ok"; data: T }
  | { kind: "unavailable" }
  | { kind: "error"; status: number; code: string; message: string };

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let res: Response;
  try {
    res = await fetch(`/api/proxy/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    return { kind: "unavailable" };
  }

  if (res.status === 503) {
    // The proxy itself sets this when the backend was unreachable --
    // see app/api/proxy/[...path]/route.ts.
    let body: { error?: { code?: string } } = {};
    try {
      body = await res.json();
    } catch {
      /* ignore -- fall through to generic unavailable */
    }
    if (body?.error?.code === "BACKEND_UNREACHABLE") {
      return { kind: "unavailable" };
    }
  }

  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* response wasn't JSON -- keep the generic message */
    }
    return { kind: "error", status: res.status, code, message };
  }

  const data = (await res.json()) as T;
  return { kind: "ok", data };
}

export const api = {
  getOverview: () => request<OpsOverviewResponse>("ops/overview"),

  listEvents: (params: {
    page?: number;
    page_size?: number;
    status?: string;
    event_type?: string;
  }) => {
    const q = new URLSearchParams();
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    if (params.status) q.set("status", params.status);
    if (params.event_type) q.set("event_type", params.event_type);
    const qs = q.toString();
    return request<EventListResponse>(`events${qs ? `?${qs}` : ""}`);
  },

  getEvent: (eventId: string) =>
    request<EventResponse>(`events/${encodeURIComponent(eventId)}`),

  getJob: (jobId: string) => request<JobDetailResponse>(`jobs/${encodeURIComponent(jobId)}`),

  listDeadLetter: (params: { page?: number; page_size?: number }) => {
    const q = new URLSearchParams();
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    const qs = q.toString();
    return request<DeadLetterListResponse>(`dead-letter${qs ? `?${qs}` : ""}`);
  },

  retryDeadLetter: (id: string) =>
    request<DeadLetterRetryResponse>(`dead-letter/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    }),
};
