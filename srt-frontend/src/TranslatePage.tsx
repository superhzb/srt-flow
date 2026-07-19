// Per-language marketing landing page, one component for every /translate/*
// route (see routes.ts). Stateless and public — no session, workflow, or app
// nav. Prerendered at build time so the copy, the real translated sample, and
// the meta tags all ship in static HTML.

import { useEffect } from "react";

import { DEMO_LINE, type LangCode } from "./demoLine.ts";
import { langMeta } from "./languages.ts";
import { LanguagePill } from "./components.tsx";
import { LegalLinks } from "./LegalLinks.tsx";
import { LANG_ROUTES } from "./routes.ts";
import { SITE_URL, translateMeta, setMeta } from "./seo.ts";
import { FlowLogo } from "./ui.tsx";

function jsonLd(source: LangCode, target: LangCode) {
  const meta = translateMeta(source, target);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        name: "srt-flow",
        applicationCategory: "MultimediaApplication",
        operatingSystem: "Web",
        description: meta.description,
        url: meta.canonical,
        offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "srt-flow",
            item: `${SITE_URL}/`,
          },
          {
            "@type": "ListItem",
            position: 2,
            name: `${langMeta(source).en} to ${langMeta(target).en}`,
            item: meta.canonical,
          },
        ],
      },
    ],
  };
}

export function TranslatePage({
  source,
  target,
}: {
  source: LangCode;
  target: LangCode;
}) {
  const from = langMeta(source).en;
  const to = langMeta(target).en;

  // Runtime meta for client-side navigation; prerender bakes the same tags in.
  useEffect(() => {
    setMeta(translateMeta(source, target));
  }, [source, target]);

  const others = LANG_ROUTES.filter((r) => r.target !== target);

  return (
    <div className="min-h-screen bg-surface text-ink">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd(source, target)),
        }}
      />
      <header className="border-b border-border/70 bg-surface/90">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-4">
          <a href="/" aria-label="srt-flow home">
            <FlowLogo />
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-5 py-16">
        <nav aria-label="Breadcrumb" className="font-mono text-xs text-faint">
          <a href="/" className="hover:text-ink">
            srt-flow
          </a>{" "}
          / {from} → {to}
        </nav>

        <h1 className="mt-6 max-w-3xl text-4xl font-semibold leading-tight tracking-[-.03em] sm:text-5xl">
          Translate {from} SRT subtitles to {to}
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-ink-muted">
          Upload a {from} <code>.srt</code> file and get {to} subtitles back in
          minutes — broadcast-ready bilingual output, auto-detected source, free
          tier with no card required.
        </p>

        <div className="mt-8">
          <a
            href="/app"
            className="inline-flex items-center gap-3 rounded-full bg-[#14181F] px-6 py-3.5 font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-accent-deep hover:shadow-xl"
          >
            Translate your {from} subtitles free →
          </a>
        </div>

        <figure className="mt-14 grid gap-4 sm:grid-cols-2">
          <figcaption className="sr-only">
            {from} to {to} subtitle sample
          </figcaption>
          <div className="rounded-2xl border border-border bg-surface-subtle p-6">
            <p className="font-mono text-[11px] uppercase tracking-wide text-faint">
              {from} source
            </p>
            <p lang={source} className="mt-3 text-lg leading-snug">
              {DEMO_LINE[source]}
            </p>
          </div>
          <div className="rounded-2xl border border-accent bg-accent-soft/40 p-6">
            <p className="font-mono text-[11px] uppercase tracking-wide text-accent-deep">
              {to} translation
            </p>
            <p lang={target} className="mt-3 text-lg leading-snug">
              {DEMO_LINE[target]}
            </p>
          </div>
        </figure>

        <section className="mt-16">
          <h2 className="text-2xl font-semibold">How it works</h2>
          <ol className="mt-5 grid gap-4 sm:grid-cols-3">
            {[
              ["01", `Drop your ${from} .srt`, "One file or a whole batch."],
              ["02", `Confirm ${to}`, "The source language is auto-detected."],
              ["03", "Download stacked", "Ready-to-use bilingual subtitles."],
            ].map(([n, t, d]) => (
              <li
                key={n}
                className="rounded-[13px] border border-border bg-surface p-5"
              >
                <span className="font-mono text-[13px] font-semibold text-accent">
                  {n}
                </span>
                <h3 className="mt-3 text-base font-semibold">{t}</h3>
                <p className="mt-2 text-sm text-ink-muted">{d}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="mt-16">
          <h2 className="text-2xl font-semibold">Other language pairs</h2>
          <div className="mt-5 flex flex-wrap gap-2">
            {others.map((r) => (
              <a
                key={r.path}
                href={r.path}
                aria-label={`Translate English to ${langMeta(r.target).en}`}
              >
                <LanguagePill code={r.target} />
              </a>
            ))}
          </div>
        </section>
      </main>

      <footer className="mt-8 bg-[#14181F] px-5 py-16 text-white">
        <div className="mx-auto flex max-w-4xl flex-col gap-10">
          <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
            <h2 className="max-w-2xl text-2xl font-semibold tracking-tight">
              Turn one {from} subtitle into every language.
            </h2>
            <a
              href="/app"
              className="whitespace-nowrap text-lg font-semibold text-cyan-400 underline-offset-4 transition hover:text-cyan-300 hover:underline"
            >
              Start free →
            </a>
          </div>
          <LegalLinks className="border-t border-white/10 pt-8" />
        </div>
      </footer>
    </div>
  );
}
