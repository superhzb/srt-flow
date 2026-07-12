// Shared client utilities: error normalisation + a fetch wrapper that
// centralises the repeated `fetch -> if(!ok) throw readError -> json` pattern.

import { SUPPORTED_LANGS, type LangCode } from "./demoLine.ts";

const SUPPORTED = new Set<string>(SUPPORTED_LANGS);

/** Default target when the visitor's language can't be resolved to a supported one. */
export const DEFAULT_TARGET: LangCode = "fr";

/** Region subtags -> language for English speakers in bilingual/other regions. */
const REGION_TO_LANG: Record<string, LangCode> = {
  CA: "fr",
  ES: "es",
  DE: "de",
  AT: "de",
  CH: "de",
  BR: "pt",
  PT: "pt",
  JP: "ja",
  KR: "ko",
  TW: "zh-TW",
  HK: "zh-TW",
  CN: "zh",
  SG: "zh",
};

/** IANA timezones -> language, a last resort for English browsers. */
const TZ_TO_LANG: Record<string, LangCode> = {
  "America/Montreal": "fr",
  "America/Toronto": "fr",
  "Europe/Paris": "fr",
  "Europe/Madrid": "es",
  "Europe/Berlin": "de",
  "Europe/Vienna": "de",
  "Europe/Zurich": "de",
  "Europe/Lisbon": "pt",
  "America/Sao_Paulo": "pt",
  "Asia/Tokyo": "ja",
  "Asia/Seoul": "ko",
  "Asia/Shanghai": "zh",
  "Asia/Taipei": "zh-TW",
  "Asia/Hong_Kong": "zh-TW",
};

/** Map one BCP-47 tag to a supported code, or null. */
function matchLang(tag: string): LangCode | null {
  const lower = tag.toLowerCase();
  // Traditional Chinese: script or region markers.
  if (
    lower.startsWith("zh") &&
    /(^|-)(hant|tw|hk|mo)(-|$)/.test(lower)
  ) {
    return "zh-TW";
  }
  if (lower.startsWith("zh")) return "zh";
  const base = lower.split("-")[0];
  return SUPPORTED.has(base) ? (base as LangCode) : null;
}

/**
 * Pick the bilingual demo's target language from the visitor's browser.
 *
 * - First supported browser language wins.
 * - English is skipped as a target (an EN+EN demo is pointless): fall back to the
 *   region subtag, then the timezone.
 * - Nothing resolves -> DEFAULT_TARGET ("fr").
 *
 * Pure: inject `langs`/`timeZone` so it stays unit-testable.
 */
export function detectTargetLang(
  langs: readonly string[] = typeof navigator !== "undefined"
    ? navigator.languages ?? [navigator.language]
    : [],
  timeZone: string = typeof Intl !== "undefined"
    ? Intl.DateTimeFormat().resolvedOptions().timeZone
    : "",
): LangCode {
  let sawEnglish = false;
  for (const tag of langs) {
    if (!tag) continue;
    const m = matchLang(tag);
    if (m && m !== "en") return m;
    if (m === "en" || tag.toLowerCase().startsWith("en")) {
      sawEnglish = true;
      // An English tag may still carry a bilingual region, e.g. "en-CA".
      const region = tag.split("-")[1]?.toUpperCase();
      if (region && REGION_TO_LANG[region]) return REGION_TO_LANG[region];
    }
  }
  if (sawEnglish && timeZone && TZ_TO_LANG[timeZone]) return TZ_TO_LANG[timeZone];
  return DEFAULT_TARGET;
}

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
