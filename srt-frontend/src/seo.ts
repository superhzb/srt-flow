// SEO metadata: one source of truth for per-page tags, shared by the runtime
// (setMeta, called from each screen's effect) and the build-time prerenderer
// (prerender-entry.tsx, which bakes the same tags into static HTML). Without
// prerender, runtime-only meta is invisible to most crawlers — see docs/plans/seo.md.

import { langMeta } from "./languages.ts";
import { LANG_SLUG } from "./routes.ts";
import type { LangCode } from "./demoLine.ts";

export const SITE_URL = "https://app.srt-flow.com";
/** 1200×630 social card. TODO: replace icon.png fallback with a real og.png. */
export const OG_IMAGE = `${SITE_URL}/og.png`;

export type PageMeta = {
  title: string;
  description: string;
  /** Absolute canonical URL. */
  canonical: string;
  ogImage?: string;
  /** e.g. "noindex, nofollow". Omitted = indexable. */
  robots?: string;
};

export const HOME_META: PageMeta = {
  title: "SRT Subtitle Translator — 9 Languages, Broadcast-Ready | srt-flow",
  description:
    "Translate .srt subtitle files into 9 languages in minutes. Auto-detected " +
    "source, broadcast-ready bilingual output, free tier — no card required.",
  canonical: `${SITE_URL}/`,
};

export function translateMeta(source: LangCode, target: LangCode): PageMeta {
  const from = langMeta(source).en;
  const to = langMeta(target).en;
  return {
    title: `Translate ${from} SRT Subtitles to ${to} | srt-flow`,
    description:
      `Translate ${from} .srt subtitle files to ${to} in minutes — ` +
      `broadcast-ready bilingual output, auto-detected source, free tier.`,
    canonical: `${SITE_URL}/translate/${LANG_SLUG[source]}-to-${LANG_SLUG[target]}/`,
  };
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Render a page's head tags as an HTML string. Used by the prerenderer to bake
 * the same tags setMeta() produces at runtime into each route's static HTML.
 */
export function metaTagsHtml(meta: PageMeta): string {
  const image = meta.ogImage ?? OG_IMAGE;
  const t = escapeAttr(meta.title);
  const d = escapeAttr(meta.description);
  const url = escapeAttr(meta.canonical);
  const img = escapeAttr(image);
  return [
    `<title>${escapeAttr(meta.title)}</title>`,
    `<meta name="description" content="${d}" />`,
    `<meta name="robots" content="${escapeAttr(meta.robots ?? "index, follow")}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:title" content="${t}" />`,
    `<meta property="og:description" content="${d}" />`,
    `<meta property="og:image" content="${img}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${t}" />`,
    `<meta name="twitter:description" content="${d}" />`,
    `<meta name="twitter:image" content="${img}" />`,
  ].join("\n    ");
}

/**
 * Mutate the document head so a client-navigated route carries its own tags.
 * Prerender bakes the same values into each page's initial HTML; this keeps
 * them correct after client-side navigation. No-op outside the browser.
 */
export function setMeta(meta: PageMeta): void {
  if (typeof document === "undefined") return;
  document.title = meta.title;
  setName("description", meta.description);
  setName("robots", meta.robots ?? "index, follow");
  setLink("canonical", meta.canonical);

  const ogImage = meta.ogImage ?? OG_IMAGE;
  setProperty("og:title", meta.title);
  setProperty("og:description", meta.description);
  setProperty("og:url", meta.canonical);
  setProperty("og:image", ogImage);
  setProperty("og:type", "website");
  setName("twitter:card", "summary_large_image");
  setName("twitter:title", meta.title);
  setName("twitter:description", meta.description);
  setName("twitter:image", ogImage);
}

function setName(name: string, content: string): void {
  upsertMeta("name", name, content);
}
function setProperty(property: string, content: string): void {
  upsertMeta("property", property, content);
}
function upsertMeta(attr: "name" | "property", key: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(
    `meta[${attr}="${key}"]`,
  );
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}
function setLink(rel: string, href: string): void {
  let el = document.head.querySelector<HTMLLinkElement>(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}
