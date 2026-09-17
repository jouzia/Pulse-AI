"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Polling, not WebSockets/SSE. Documented choice (see Step 12 of the
 * Phase 5 brief): the backend's own data sources are already pull-based
 * -- Prometheus counters are scraped, not pushed, and the database
 * aggregates in app/services/ops_service.py are point-in-time queries,
 * not a change stream. Adding a WebSocket layer would mean building and
 * running a second, unnecessary distributed subsystem (a pub/sub
 * fan-out from the API process) to push data that is itself only ever
 * computed on demand. A dashboard polling every 15s is simple, has no
 * additional moving parts, and matches how an operator would actually
 * use this: checking in periodically, not watching a live feed pixel by
 * pixel.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 15000
): { data: T | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(() => {
    fetcherRef.current().then(setData);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { data, refresh };
}
