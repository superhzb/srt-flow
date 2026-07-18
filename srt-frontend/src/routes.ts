// Public marketing routes. English is the fixed source for v1; extend to a
// full source×target matrix later if the top pages earn traffic.
//
// These pages are prerendered at build time (scripts/prerender.mjs) so each URL
// ships real HTML — that is what makes them indexable and social-previewable.
// The same LANG_ROUTES list feeds sitemap generation and the landing-page pill
// links, so URLs stay in sync from one source.

import { SUPPORTED_LANGS, type LangCode } from "./demoLine.ts";

/** URL slug per language, used in /translate/english-to-<slug>. */
export const LANG_SLUG: Record<LangCode, string> = {
  en: "english",
  es: "spanish",
  zh: "chinese-simplified",
  "zh-TW": "chinese-traditional",
  fr: "french",
  de: "german",
  pt: "portuguese",
  ja: "japanese",
  ko: "korean",
};

export type LangRoute = { path: string; source: LangCode; target: LangCode };

// Trailing slash is the canonical form: StaticFiles(html=True) serves the
// directory's index.html at /translate/x/ and 307-redirects /translate/x to it,
// so linking and canonicalizing with the slash avoids a redirect hop.
export const LANG_ROUTES: LangRoute[] = SUPPORTED_LANGS.filter(
  (t) => t !== "en",
).map((target) => ({
  path: `/translate/${LANG_SLUG.en}-to-${LANG_SLUG[target]}/`,
  source: "en" as LangCode,
  target,
}));

export function matchLangRoute(pathname: string): LangRoute | undefined {
  // Tolerate a missing trailing slash so /translate/x and /translate/x/ both
  // resolve to the same page.
  const normalized = pathname.endsWith("/") ? pathname : `${pathname}/`;
  return LANG_ROUTES.find((r) => r.path === normalized);
}

/** Every public URL, for sitemap generation and prerendering. */
export const PUBLIC_ROUTES: string[] = ["/", ...LANG_ROUTES.map((r) => r.path)];
