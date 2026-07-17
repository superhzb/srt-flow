// Explicit client-side event tracking.
//
// Call track() at meaningful moments only — we deliberately do NOT
// auto-instrument fetch (noisy, low-value). Events buffer briefly, then
// POST to /api/events as a batch. Best-effort: failures are swallowed so
// analytics never breaks a user flow. /api/events is never itself tracked.

import { getAnonId, getSessionId } from "./clientStorage.ts";

export type ClientEventType = "screen_viewed" | "demo_started" | "cta_clicked";

interface QueuedEvent {
  event_type: ClientEventType;
  props: Record<string, unknown>;
}

const MAX_BATCH = 20;
const FLUSH_DELAY_MS = 2000;
const ENDPOINT = "/api/events";

const buffer: QueuedEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function envelope(events: QueuedEvent[]): string {
  return JSON.stringify({
    events,
    session_id: getSessionId(),
    anon_id: getAnonId(),
  });
}

export function track(
  event_type: ClientEventType,
  props: Record<string, unknown> = {},
): void {
  buffer.push({ event_type, props });
  if (buffer.length >= MAX_BATCH) {
    void flush();
    return;
  }
  if (timer === null) timer = setTimeout(() => void flush(), FLUSH_DELAY_MS);
}

export async function flush(): Promise<void> {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
  if (buffer.length === 0) return;
  const events = buffer.splice(0, MAX_BATCH);
  try {
    await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: envelope(events),
      keepalive: true,
    });
  } catch {
    // Best-effort — drop on failure.
  }
}

// Flush whatever is buffered when the page is hidden/closed.
if (typeof window !== "undefined") {
  window.addEventListener("pagehide", () => {
    if (buffer.length === 0) return;
    const events = buffer.splice(0, MAX_BATCH);
    const blob = new Blob([envelope(events)], { type: "application/json" });
    navigator.sendBeacon?.(ENDPOINT, blob);
  });
}
