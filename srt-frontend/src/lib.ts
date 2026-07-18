// Shared client utilities: error normalisation + a fetch wrapper that
// centralises the repeated `fetch -> if(!ok) throw readError -> json` pattern.

// FastAPI HTTPException detail can be a string or a list of field errors;
// normalise both into a single message.
function extractDetail(maybe: unknown, fallback: string): string {
  if (typeof maybe === "string") return maybe;
  if (Array.isArray(maybe) && maybe.length > 0) {
    const first = maybe[0];
    if (first && typeof first === "object" && "msg" in first) {
      return String((first as { msg: unknown }).msg);
    }
  }
  return fallback;
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  let body: unknown = undefined;
  try {
    body = await resp.json();
  } catch {
    // fall through with generic message
  }
  const detail =
    body && typeof body === "object" && "detail" in body
      ? extractDetail((body as { detail: unknown }).detail, fallback)
      : fallback;
  return new Error(detail);
}

/** Coerce a thrown value into a human message, falling back when it's not an Error. */
export function errMessage(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

/**
 * fetch + non-ok → Error + json cast. Replaces the ~15 hand-rolled copies in
 * api.ts. The status-specific endpoints (401/402 handling) stay manual.
 */
export async function apiFetch<T>(
  url: string,
  init?: RequestInit,
  fallback = "request failed",
): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) throw await readError(resp, `${fallback} (${resp.status})`);
  return (await resp.json()) as T;
}

export function formatCurrency(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

export function formatLedgerDate(value: string): string {
  const date = new Date(value);
  const elapsed = Date.now() - date.getTime();
  if (elapsed >= 0 && elapsed < 60_000) return "Just now";
  if (elapsed >= 0 && elapsed < 3_600_000) {
    return `${Math.floor(elapsed / 60_000)}m ago`;
  }
  if (elapsed >= 0 && elapsed < 86_400_000) {
    return `${Math.floor(elapsed / 3_600_000)}h ago`;
  }
  if (elapsed >= 0 && elapsed < 172_800_000) return "Yesterday";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
