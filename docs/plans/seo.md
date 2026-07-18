# SEO Plan — srt-flow

Goal: increase organic exposure and traffic for the SRT subtitle translator
(`www.srt-flow.com`).

## Diagnosis

Current state:

- React SPA (Vite, client-rendered). FastAPI serves `srt-frontend/dist/` as
  static files with an SPA fallback (`SpaStaticFiles` in
  `srt-backend/src/srt_backend/app.py`).
- `index.html` `<title>` is just `"srt-flow"`. No meta description, no
  canonical, no Open Graph / Twitter cards, no `hreflang`, no JSON-LD.
- No `robots.txt`, no `sitemap.xml`, no web manifest.
- All marketing copy lives in `LandingScreen.tsx` and is client-rendered. The
  initial HTML is an empty `<div id="root">`. Crawlers must execute JS to see
  any content; Google can (slowly, unreliably), most others (Bing, social
  scrapers, LLM crawlers) cannot.
- Single URL (`/`). Zero content pages = zero keyword surface. Missing intent
  like "translate srt online", "srt subtitle translator", per-language queries.
- Google Fonts are render-blocking, hurting LCP (a Core Web Vitals ranking
  factor).
- No `h1`/text in static HTML.

Root problem: **SPA is invisible to crawlers, and there is no content
footprint.** Both must be fixed. Phases 1 and 2 are table stakes; Phase 3
content stays invisible without them.

## Phase 1 — Technical foundation (fast wins, ~1 day)

Ship first. Low effort, raises the floor.

1. **`index.html` meta** — real `<title>` (~55 chars, keyword-front), e.g.
   `SRT Subtitle Translator — 9 Languages, Broadcast-Ready | srt-flow`. Add
   `<meta name="description">` (~155 chars), `<link rel="canonical">`, Open
   Graph tags (`og:title`, `og:description`, `og:image`, `og:url`, `og:type`),
   and a Twitter card. Provide an `og:image` (1200×630) derived from
   `cockpit.webp` + logo.
2. **`robots.txt`** in `srt-frontend/public/` — allow all, reference the
   sitemap, disallow `/admin` and `/api`.
3. **`sitemap.xml`** in `srt-frontend/public/` — list all public URLs (grows
   with Phase 3).
4. **`manifest.webmanifest`** — name, icons (reuse `public/icon.png`), theme
   color.
5. **Fonts** — self-host, or `preload` + `font-display: swap`. Drop CJK weights
   not needed at first paint to improve LCP.
6. **`/admin`** — confirm `noindex`; keep it out of the sitemap.

## Phase 2 — Rendering (make content crawlable, biggest lever)

SPA content must exist in the HTML at request time.

Options, ranked:

- **A (recommended): build-time prerender.** Use `vite-plugin-prerender` /
  `react-snap` / a Puppeteer step to render `/` (and future content pages) to
  static HTML at build time. App still hydrates. No infra change — FastAPI keeps
  serving `dist/`. Cheapest given the current static-serve topology.
- **B: SSR.** Migrate to Next.js/Remix or add Vite SSR. Best long-term, but a
  heavy rewrite. Overkill now.
- **C: dynamic prerender.** Serve prerendered HTML to bots via a service
  (Prerender.io) at the FastAPI layer. Middle cost, monthly fee.

Do **A**. Landing copy (h1, how-it-works, languages, pricing) then lands in
static HTML → indexable and social previews work.

## Phase 3 — Per-language landing pages (traffic engine)

A single-page SPA ranks for almost nothing but its brand name. This project
needs *some* keyword surface — but scoped, template-driven, not a content
operation.

**In scope — do this:**

- **Per-language landing pages**, generated from one template + the existing
  language data (`demoLine.ts` `SUPPORTED_LANGS`, `LANG_LABEL`, `DEMO_LINE`).
  URLs like `/translate/english-to-japanese`, `/translate/english-to-french`.
  Each has a unique `<h1>`, `<title>`, meta description, a real translated
  sample (already have `DEMO_LINE`), and a CTA into the app. Targets exact
  buyer intent ("translate english subtitles to japanese") at low competition.
  This is the actual traffic lever.
- Wire each page into `sitemap.xml`, and link them internally (see below).
- Start with the top ~3 target languages, then fill out the rest. 8 target
  languages (English as fixed source) ≈ 8 pages from one component; expand to
  full source×target matrix later only if the top pages earn traffic.

**Landing-page change required:** the 9 language pills in `LandingScreen.tsx`
(`SUPPORTED_LANGS.map` → `LanguagePill`) are currently decoration. Turn them
into links (`<a href="/translate/english-to-…">`) so crawlers discover the new
pages and link equity flows. This is a UI tweak, not a new "button/feature".

**Out of scope for now (optional, later, only if content ROI proves out):**
blog, glossary/explainer pages ("what is an SRT file"), broad use-case pages.
These need ongoing writing labor and have higher competition; low priority for
a niche tool.

See "Router + template sketch" below for implementation.

## Phase 4 — Off-page + measurement (compounding)

1. **Google Search Console + Bing Webmaster Tools** — verify domain, submit
   sitemap, monitor coverage and queries. Do immediately, in parallel with
   Phase 1.
2. **Structured data** — JSON-LD `SoftwareApplication` + `FAQPage`
   (pricing/how-it-works) for rich results.
3. **Analytics** — first-party event tracking already exists (commit
   `7b846fc`). Add search-referral segmentation; GA4 or Plausible for
   acquisition.
4. **Backlinks** — list on tool directories (Product Hunt, AlternativeTo,
   subtitle/localization forums, r/languagelearning). Cheap early authority.
5. **`hreflang`** — once the UI is localized.

## Priority sequence

```
Week 1:    Phase 1 (meta / robots / sitemap / manifest) + GSC/Bing verify
Week 1-2:  Phase 2 (build-time prerender)               ← unlocks everything
Week 2+:   Phase 3 per-language pages (top 3 languages first)
Ongoing:   Phase 4 backlinks; optional content only if ROI proves out
```

## Router + template sketch (Phase 3 implementation)

Current routing is manual: `App.tsx` keys off `window.location.pathname` +
`window.history.replaceState`, with `TAB_PATHS` for `/app`, `/app/jobs`,
`/app/billing`, and `showLanding` for `/`. No router library. The backend
`SpaStaticFiles` (`srt-backend/src/srt_backend/app.py`) serves `index.html` as
the SPA fallback for any unmatched path.

The marketing pages must be **crawlable at request time**, so they depend on
Phase 2 (prerender) to emit real HTML per URL. Two viable approaches:

### Approach 1 — Extend the existing manual router (lightest)

Add a public route table alongside `TAB_PATHS`. No new dependency.

```ts
// routes.ts — English as fixed source for v1; extend to a matrix later.
import { SUPPORTED_LANGS, LANG_LABEL, DEMO_LINE, type LangCode } from "./demoLine";

export const LANG_SLUG: Record<LangCode, string> = {
  en: "english", es: "spanish", zh: "chinese-simplified",
  "zh-TW": "chinese-traditional", fr: "french", de: "german",
  pt: "portuguese", ja: "japanese", ko: "korean",
};

export type LangRoute = { path: string; source: LangCode; target: LangCode };

// /translate/english-to-<target> for every target except English.
export const LANG_ROUTES: LangRoute[] = SUPPORTED_LANGS
  .filter((t) => t !== "en")
  .map((target) => ({
    path: `/translate/english-to-${LANG_SLUG[target]}`,
    source: "en",
    target,
  }));

export function matchLangRoute(pathname: string): LangRoute | undefined {
  return LANG_ROUTES.find((r) => r.path === pathname);
}
```

`App.tsx` top-level: before the app/landing switch, check for a marketing
route and render the template instead. These pages are public and stateless —
they don't need session, workflow, or the app nav.

```tsx
const langRoute = matchLangRoute(window.location.pathname);
if (langRoute) return <TranslatePage {...langRoute} />;
```

### Approach 2 — Adopt `react-router`

If more content routes are coming, `react-router-dom` is cleaner than growing
the manual switch: a `<BrowserRouter>` with `/translate/:pair` and a loader
that resolves the pair to a `LangRoute`. Heavier, but standard, and prerender
tooling understands it. Recommended only if the route count grows past a
handful.

**Pick Approach 1 for v1** (8 pages, no new dep). Migrate to Approach 2 if the
matrix expands.

### The template component

One component renders every per-language page from the route's `source`/
`target`. Reuse `DEMO_LINE` for a real sample and existing UI primitives.

```tsx
// TranslatePage.tsx
import { LANG_LABEL, DEMO_LINE, type LangCode } from "./demoLine";
import { setMeta } from "./seo"; // sets <title>/<meta>/canonical at runtime

const NAME: Record<LangCode, string> = {
  en: "English", es: "Spanish", zh: "Simplified Chinese",
  "zh-TW": "Traditional Chinese", fr: "French", de: "German",
  pt: "Portuguese", ja: "Japanese", ko: "Korean",
};

export function TranslatePage({ source, target }: { source: LangCode; target: LangCode }) {
  const from = NAME[source], to = NAME[target];
  setMeta({
    title: `Translate ${from} SRT Subtitles to ${to} | srt-flow`,
    description: `Translate ${from} .srt subtitle files to ${to} in minutes — `
      + `broadcast-ready bilingual output, auto-detected source, free tier.`,
    canonical: `https://www.srt-flow.com/translate/${source === "en" ? "english" : source}-to-${to.toLowerCase()}`,
  });
  return (
    <main>
      <h1>{from} → {to} subtitle translation</h1>
      <p>Upload a {from} .srt and get {to} subtitles back, formatted and ready.</p>
      <figure>
        <p lang={source}>{DEMO_LINE[source]}</p>
        <p lang={target}>{DEMO_LINE[target]}</p>  {/* real sample, indexable */}
      </figure>
      <a href="/app">Translate your {from} subtitles free →</a>
      {/* JSON-LD SoftwareApplication + BreadcrumbList here */}
    </main>
  );
}
```

Key points:

- `setMeta` mutates `document.title`/meta tags at runtime so each route has
  unique tags. Prerender (Phase 2) then bakes them into each page's static
  HTML — that is what makes them index/preview correctly. Without prerender,
  runtime-only meta is invisible to most crawlers.
- The translated `DEMO_LINE[target]` in the markup gives each page unique,
  real, on-topic text — not boilerplate.
- Each `LANG_ROUTES` entry also feeds `sitemap.xml` generation and the
  landing-page pill links.

### Landing-page pill links

In `LandingScreen.tsx`, the `SUPPORTED_LANGS.map(...LanguagePill)` block wraps
each pill in a link to its page, so the pages are internally linked and
crawler-discoverable:

```tsx
{SUPPORTED_LANGS.filter((c) => c !== "en").map((code) => (
  <a key={code} href={`/translate/english-to-${LANG_SLUG[code]}`}>
    <LanguagePill code={code} />
  </a>
))}
```

### Wiring checklist

- [ ] `routes.ts`: `LANG_SLUG`, `LANG_ROUTES`, `matchLangRoute`.
- [ ] `TranslatePage.tsx` template + `seo.ts` `setMeta` helper.
- [ ] `App.tsx`: match marketing route before the landing/app switch.
- [ ] `LandingScreen.tsx`: pills → links.
- [ ] `sitemap.xml`: include every `LANG_ROUTES` path (Phase 1/generation).
- [ ] Prerender config (Phase 2): render `/` + every `LANG_ROUTES` path.
- [ ] Backend `SpaStaticFiles`: confirm the prerendered per-route HTML is
      served (not the generic `index.html`) for these paths.
