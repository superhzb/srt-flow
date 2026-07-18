# 08 — SEO, Prerendering & Landing Routes

srt-flow is a client-rendered React SPA, so its SEO surface is manufactured at
build time: `srt-frontend` ships static meta tags in `index.html`, a
`robots.txt` / `site.webmanifest` in `public/`, and a post-build prerender step
that renders every public route to its own static `index.html` (with baked-in
meta and real HTML content) plus a generated `sitemap.xml`. Per-language
`/translate/english-to-<lang>/` landing pages are driven from one route table
and one template component, and the FastAPI backend serves the whole
prerendered `dist/` tree as static files (see doc 01).

## Static head defaults — `srt-frontend/index.html`

The shipped `index.html` carries the home-page defaults inside a marker block:

```html
<!-- seo:start — home defaults; scripts/prerender.mjs replaces this block per route -->
...
<!-- seo:end -->
```

Inside the block: `<title>`, `<meta name="description">`,
`<meta name="robots" content="index, follow">`, `<link rel="canonical">`, the
Open Graph set (`og:type`, `og:url`, `og:title`, `og:description`, `og:image`),
and the Twitter card set (`twitter:card=summary_large_image`, `twitter:title`,
`twitter:description`, `twitter:image`). These values match `HOME_META` in
`seo.ts`. Outside the block, the head also declares `theme-color`,
`<link rel="icon" href="/icon.png">`, `<link rel="manifest" href="/site.webmanifest">`,
and loads Google Fonts non-render-blocking (`media="print"` + `onload` swap,
with a `<noscript>` fallback). The prerenderer rewrites everything between the
`seo:start`/`seo:end` markers per route; the rest of the head is constant.

## Static assets — `srt-frontend/public/`

- `robots.txt` — `Allow: /`, `Disallow: /admin`, `Disallow: /api`, and a
  `Sitemap: https://www.srt-flow.com/sitemap.xml` reference.
- `site.webmanifest` — name/short_name, description, `start_url: /`,
  `display: standalone`, background + theme color `#14181F`, and one
  `/icon.png` (512×512, `any maskable`) icon.
- `icon.png`, `og.png` — favicon and the 1200×630 social card
  (`OG_IMAGE = https://www.srt-flow.com/og.png` in `seo.ts`).

Vite copies `public/` verbatim into `dist/` at build.

## Build-time prerender

`package.json` build chains the prerender after the Vite build:

```
"build": "tsc -b && vite build && node scripts/prerender.mjs"
```

`scripts/prerender.mjs` uses Vite's programmatic SSR
(`createServer` + `ssrLoadModule`) — no headless browser. It:

1. Reads `dist/index.html` as the template and asserts the `<!-- seo:start`
   marker and `<div id="root"></div>` are present (`scripts/prerender.mjs`).
2. Loads `renderRoute` from `src/prerender-entry.tsx`, `PUBLIC_ROUTES` from
   `src/routes.ts`, and `SITE_URL` from `src/seo.ts`.
3. For each route, calls `renderRoute(route)` → `{ appHtml, headTags }`,
   replaces the `seo:start…seo:end` block with `headTags`, and injects `appHtml`
   into `<div id="root">…</div>`.
4. Writes the output: `/` → `dist/index.html`; `/translate/x/` →
   `dist/translate/x/index.html` (`scripts/prerender.mjs`).
5. Emits `dist/sitemap.xml` from `PUBLIC_ROUTES` (home `priority 1.0`, others
   `0.8`, all `changefreq weekly`).

`src/prerender-entry.tsx:renderRoute` dispatches on the pathname: a match from
`matchLangRoute` renders `<TranslatePage>` with `translateMeta`; everything else
(including `/`) falls back to `<LandingScreen signedIn={false}>` with
`HOME_META`. It uses `renderToStaticMarkup` because the client mounts with
`createRoot().render` (not `hydrateRoot`) — the prerendered markup is discarded
on load and exists purely for crawlers, so no hydration-mismatch rules apply.

## Per-language landing routes

`src/routes.ts` is the single source of route truth:

- `LANG_SLUG` — `Record<LangCode, string>` mapping each language to a URL slug.
- `LANG_ROUTES` — built from `SUPPORTED_LANGS` (in `demoLine.ts`) minus `en`;
  one `{ path, source: "en", target }` per target. Paths use a **trailing
  slash** as canonical form, matching `StaticFiles(html=True)` directory
  serving (bare paths 307-redirect to the slash).
- `matchLangRoute(pathname)` — normalizes a missing trailing slash, then finds
  the matching `LangRoute`.
- `PUBLIC_ROUTES` — `["/", ...LANG_ROUTES paths]`, consumed by the prerenderer
  and sitemap generator.

### Prerendered routes → slug → target language

Source is always English (`en`). English itself has no page (it is the fixed
source).

| Route (prerendered) | Slug | Target `LangCode` |
| --- | --- | --- |
| `/` | — | home / landing |
| `/translate/english-to-spanish/` | spanish | `es` |
| `/translate/english-to-chinese-simplified/` | chinese-simplified | `zh` |
| `/translate/english-to-chinese-traditional/` | chinese-traditional | `zh-TW` |
| `/translate/english-to-french/` | french | `fr` |
| `/translate/english-to-german/` | german | `de` |
| `/translate/english-to-portuguese/` | portuguese | `pt` |
| `/translate/english-to-japanese/` | japanese | `ja` |
| `/translate/english-to-korean/` | korean | `ko` |

8 language pages + home = 9 entries in `PUBLIC_ROUTES` and `sitemap.xml`.

### Template — `src/TranslatePage.tsx`

One stateless component renders every `/translate/*` page from its
`source`/`target` props. It emits an `<h1>` ("Translate {from} SRT subtitles to
{to}"), intro copy, a `/app` CTA, a real bilingual sample from
`DEMO_LINE[source]` / `DEMO_LINE[target]` (unique on-topic text per page), a
"How it works" section, and "Other language pairs" pills linking the sibling
routes (`LANG_ROUTES` filtered to exclude the current target). It also inlines a
JSON-LD `@graph` (`SoftwareApplication` + `BreadcrumbList`) via
`dangerouslySetInnerHTML`. A `useEffect` calls `setMeta(translateMeta(...))` so
client-side navigation carries the right tags; the prerender bakes the identical
tags into the static HTML.

### Meta helper — `src/seo.ts`

`seo.ts` is the one source of truth for per-page tags, shared by runtime and
prerender:

- `SITE_URL`, `OG_IMAGE`, `HOME_META`, and `translateMeta(source, target)`
  (builds title/description/canonical for a pair).
- `metaTagsHtml(meta)` — renders the tag set as an escaped HTML string; used by
  the prerenderer to bake tags in.
- `setMeta(meta)` — mutates `document.title`, description, robots, canonical
  link, and the OG/Twitter meta tags at runtime (upserting each); no-op outside
  the browser. Runtime and build-time paths produce the same tag set.

### Route dispatch — `src/main.tsx`

The client entry checks `matchLangRoute(window.location.pathname)` once at mount:
a match renders `<TranslatePage>`; otherwise it renders `<App />` (the app SPA).
No router library is used.

### Pill links — `src/LandingScreen.tsx`

The home languages section maps `SUPPORTED_LANGS` to `LanguagePill`s: `en`
renders a plain pill (no page), every other code wraps its pill in
`<a href="/translate/english-to-<slug>/">`, so crawlers discover the landing
pages and internal link equity flows.

## Backend static serving

The backend serves the entire prerendered `dist/` tree — see doc 01 for the full
static-serving design. In short, `srt-backend/src/srt_backend/app.py` mounts
`SpaStaticFiles(directory=dist, html=True)` at `/`. `html=True` serves each
route's `dist/<route>/index.html` directly, so prerendered pages ship their own
baked HTML rather than the generic SPA shell. `SpaStaticFiles.get_response`
falls back to `index.html` on 404 (except under `assets/`, which 404s hard), and
sets `Cache-Control: immutable` for hashed `/assets/*` and `no-cache` elsewhere.
An `_noindex_admin` middleware adds `X-Robots-Tag: noindex, nofollow` to
`/admin*` responses (belt-and-suspenders with the `robots.txt` disallow).

## Operational checklist (off-page)

These are ongoing operational tasks, not code state — they live outside the
repo and are not verifiable from source:

- [ ] Google Search Console + Bing Webmaster Tools — verify the domain, submit
      `sitemap.xml`, monitor coverage and query performance.
- [ ] Backlinks — list on tool directories (Product Hunt, AlternativeTo,
      subtitle/localization communities) to build early authority.
- [ ] `hreflang` — add once the UI itself is localized (not yet applicable;
      current landing pages target English-speaking searchers).
