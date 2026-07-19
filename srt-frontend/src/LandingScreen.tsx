import { useEffect, useState } from "react";

import { googleLoginUrl, startCheckout, type CreditPack } from "./api.ts";
import { LanguagePill } from "./components.tsx";
import { LegalLinks } from "./LegalLinks.tsx";
import { langMeta } from "./languages.ts";
import { LANG_SLUG } from "./routes.ts";
import {
  DEMO_LINE,
  LANG_LABEL,
  SUPPORTED_LANGS,
  type LangCode,
} from "./demoLine.ts";
import { Button, Card, MonoLabel } from "./ui.tsx";
import cockpit from "./assets/cockpit.webp";

const LANDING_DEMO_LANGS: readonly LangCode[] = [
  "zh",
  "fr",
  ...SUPPORTED_LANGS.filter(
    (code) => code !== "en" && code !== "zh" && code !== "fr",
  ),
];
const LANDING_DEMO_INTERVAL_MS = 4000;

const login = () => {
  window.location.href = googleLoginUrl();
};

export function LandingScreen({
  signedIn = false,
  onOpenApp,
  onOpenStudio,
}: {
  signedIn?: boolean;
  onOpenApp?: () => void;
  onOpenStudio?: () => void;
} = {}) {
  const [demoLanguageIndex, setDemoLanguageIndex] = useState(0);
  const demoLanguage = LANDING_DEMO_LANGS[demoLanguageIndex];
  const primaryAction = signedIn && onOpenApp ? onOpenApp : login;
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

    const interval = window.setInterval(() => {
      setDemoLanguageIndex(
        (current) => (current + 1) % LANDING_DEMO_LANGS.length,
      );
    }, LANDING_DEMO_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, []);
  const paidAction = (pack: CreditPack) => {
    if (!signedIn) return login();
    void startCheckout(pack).then(({ url }) => {
      window.location.href = url;
    });
  };
  return (
    <div className="min-h-screen bg-surface text-ink">
      <section className="mx-auto max-w-6xl px-5 pb-24 pt-16 text-center sm:pt-24">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-subtle px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-ink-muted">
          <span className="pulse-dot h-2 w-2 rounded-full bg-accent" />9
          languages · auto-detected source
        </div>
        <h1 className="mx-auto mt-7 max-w-4xl text-5xl font-semibold leading-[.98] tracking-[-.065em] sm:text-7xl">
          One subtitle in.
          <br />
          <span className="gradient-text">Every language out.</span>
        </h1>
        <p className="mx-auto mt-7 max-w-2xl text-lg text-ink-muted">
          Turn one SRT into broadcast-ready subtitles for every audience—in
          minutes, not weeks.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <button
            type="button"
            onClick={primaryAction}
            className="inline-flex items-center justify-center gap-3 rounded-full bg-[#14181F] px-6 py-3.5 font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-accent-deep hover:shadow-xl active:translate-y-0 active:scale-95"
          >
            {!signedIn && <GoogleIcon />}
            {signedIn ? "Open workspace" : "Continue with Google"}
          </button>
          {!signedIn && (
            <button
              type="button"
              onClick={onOpenStudio ?? primaryAction}
              className="rounded-full border border-border bg-surface px-6 py-3.5 font-semibold text-ink shadow-sm transition hover:-translate-y-0.5 hover:border-ink/40 hover:bg-surface-inset hover:shadow-md active:translate-y-0 active:scale-95"
            >
              Live demo
            </button>
          )}
        </div>
        <p className="mt-4 font-mono text-[11px] text-faint">
          Free tier · no card · 30 min of subtitles / month
        </p>
        <div className="relative mt-20 grid gap-12 text-left md:grid-cols-2 md:gap-8">
          <VideoDemo>
            <p>{DEMO_LINE.en}</p>
          </VideoDemo>
          <TransformationArrow />
          <VideoDemo badge={`EN + ${LANG_LABEL[demoLanguage]}`}>
            <p key={demoLanguage} className="rise font-normal text-[#FFE066]">
              {DEMO_LINE[demoLanguage]}
            </p>
            <p>{DEMO_LINE.en}</p>
          </VideoDemo>
        </div>
      </section>
      <section
        id="howitworks"
        className="scroll-mt-24 border-y border-border bg-surface-subtle px-5 py-24"
      >
        <div className="mx-auto max-w-6xl">
          <div>
            <MonoLabel>How it works</MonoLabel>
            <h2 className="mt-4 text-3xl font-semibold tracking-tight">
              Three steps. Zero friction.
            </h2>
            <p className="mt-3 max-w-xl text-ink-muted">
              Upload once, choose your audience, and download a ready-to-use
              bilingual subtitle file.
            </p>
          </div>
          <div className="mt-9 grid gap-5 md:grid-cols-3">
            {[
              [
                "01",
                "Drop your .srt",
                "One file or a whole batch. We auto-detect the source language instantly.",
              ],
              [
                "02",
                "Pick languages",
                "Choose up to three target languages — they all run in parallel.",
              ],
              [
                "03",
                "Download stacked",
                "Reorder any language to the top and re-download instantly — no re-translating, ever.",
              ],
            ].map(([n, t, d]) => (
              <article
                key={n}
                className="rounded-[13px] border border-border bg-surface p-[26px]"
              >
                <span className="font-mono text-[13px] font-semibold text-accent">
                  {n}
                </span>
                <h3 className="mt-3.5 text-lg font-semibold tracking-[-.01em]">
                  {t}
                </h3>
                <p className="mt-2 text-sm leading-6 text-ink-muted">{d}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
      <section id="languages" className="scroll-mt-24 px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <MonoLabel>languages</MonoLabel>
          <h2 className="mt-4 text-3xl font-semibold">
            Speak to the whole room.
          </h2>
          <p className="mt-4 max-w-xl text-ink-muted">
            Translate between English, Español, 简体中文, 繁體中文, Français,
            Deutsch, Português, 日本語, and 한국어.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {SUPPORTED_LANGS.map((code) =>
              code === "en" ? (
                // English is the fixed source; it has no per-language page.
                <LanguagePill key={code} code={code} />
              ) : (
                <a
                  key={code}
                  href={`/translate/${LANG_SLUG.en}-to-${LANG_SLUG[code]}/`}
                  aria-label={`Translate English to ${langMeta(code).en}`}
                >
                  <LanguagePill code={code} />
                </a>
              ),
            )}
          </div>
        </div>
      </section>
      <section
        id="pricing"
        className="scroll-mt-24 border-t border-border bg-surface-subtle px-5 py-24"
      >
        <div className="mx-auto max-w-6xl">
          <MonoLabel>simple pricing</MonoLabel>
          <h2 className="mt-4 text-3xl font-semibold">
            Start free. Pay once when you need more.
          </h2>
          <p className="mt-4 text-ink-muted">
            Buy minutes, not a subscription. Metered by source length × target
            language — one language costs its minutes, three cost 3×.
          </p>
          <div className="mt-9 grid gap-6 md:grid-cols-3">
            {[
              {
                name: "Free",
                price: "$0",
                minutes: "30 min / month",
                unit: "No card required",
                features: "9 languages · real trial",
                cta: "Start free",
                pack: null,
              },
              {
                name: "Small pack",
                price: "$3.99",
                minutes: "100 min",
                unit: "$0.040/min",
                features: "9 languages · ~1–2 shows",
                cta: "Buy 100 min",
                pack: "small" as const,
              },
              {
                name: "Large pack",
                price: "$29.99",
                minutes: "1000 min",
                unit: "$0.030/min",
                features: "9 languages · ~25 shows",
                cta: "Buy 1000 min",
                pack: "large" as const,
                badge: "Best value · 25% off",
              },
            ].map((plan) => (
              <Card
                key={plan.name}
                className={`relative flex flex-col p-6 ${plan.pack === "large" || (signedIn && !plan.pack) ? "border-accent" : ""}`}
              >
                {signedIn && !plan.pack && (
                  <span className="absolute right-4 top-4 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-deep">
                    Current plan
                  </span>
                )}
                {plan.badge && (
                  <span className="absolute right-4 top-4 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent">
                    {plan.badge}
                  </span>
                )}
                <h3 className="font-semibold">{plan.name}</h3>
                <p className="mt-4 text-4xl font-semibold gradient-text">
                  {plan.price}
                </p>
                <p className="mt-5 text-xl font-semibold">{plan.minutes}</p>
                <p className="mt-1 text-sm text-ink-muted">{plan.unit}</p>
                <p className="mb-6 mt-5 text-sm text-ink-muted">
                  {plan.features}
                </p>
                <Button
                  className="mt-auto w-full"
                  disabled={signedIn && !plan.pack}
                  onClick={
                    plan.pack ? () => paidAction(plan.pack) : primaryAction
                  }
                >
                  {signedIn && !plan.pack ? "Current plan" : plan.cta}
                </Button>
              </Card>
            ))}
          </div>
          <div className="mt-7 rounded-full border border-border bg-surface px-4 py-2 text-center text-sm text-ink-muted">
            No card for free · one-time payment · no auto-renew
          </div>
        </div>
      </section>
      <footer className="bg-[#14181F] px-5 py-20 text-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-10">
          <div className="flex flex-col items-start justify-between gap-8 sm:flex-row sm:items-center">
            <h2 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
              Learn a language from the videos you already love.
            </h2>
            <button
              type="button"
              onClick={primaryAction}
              className="whitespace-nowrap text-lg font-semibold text-cyan-400 underline-offset-4 transition hover:text-cyan-300 hover:underline active:scale-95"
            >
              {signedIn ? "Open workspace →" : "Start free →"}
            </button>
          </div>
          <LegalLinks className="border-t border-white/10 pt-8" />
        </div>
      </footer>
    </div>
  );
}

function VideoDemo({
  badge,
  children,
}: {
  /** Bilingual badge text, e.g. "EN + FR". Absent = monolingual card. */
  badge?: string;
  children: React.ReactNode;
}) {
  const translated = badge !== undefined;
  return (
    <div className="min-w-0">
      <div
        className="relative flex aspect-video flex-col items-center justify-end overflow-hidden rounded-2xl bg-[#090A0D] bg-cover bg-center px-7 pb-3 pt-7 text-center text-white shadow-xl"
        style={{ backgroundImage: `url(${cockpit})` }}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-black/10" />
        <div className="relative space-y-1 rounded-lg bg-black/25 px-4 py-2 text-lg leading-snug font-normal backdrop-blur-[2px] [text-shadow:0_1px_4px_rgba(0,0,0,.9)] sm:text-xl">
          {children}
        </div>
        {translated && (
          <span
            key={badge}
            className="rise absolute right-4 top-4 rounded-full bg-accent px-2.5 py-1 font-mono text-[10px] font-semibold text-white"
          >
            {badge}
          </span>
        )}
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      viewBox="0 0 18 18"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        fill="#4285F4"
        d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.797 2.716v2.258h2.909c1.702-1.567 2.684-3.875 2.684-6.614Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.468-.806 5.956-2.181l-2.909-2.258c-.806.54-1.835.859-3.047.859-2.344 0-4.328-1.585-5.037-3.714H.956v2.333A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.963 10.706A5.41 5.41 0 0 1 3.682 9c0-.592.102-1.168.281-1.706V4.961H.956A9 9 0 0 0 0 9c0 1.452.347 2.827.956 4.039l3.007-2.333Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.507.454 3.441 1.346l2.581-2.581C13.464.892 11.426 0 9 0A9 9 0 0 0 .956 4.961l3.007 2.333C4.672 5.165 6.656 3.58 9 3.58Z"
      />
    </svg>
  );
}

function TransformationArrow() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute left-1/2 top-1/2 z-10 grid h-16 w-16 -translate-x-1/2 -translate-y-1/2 rotate-90 place-items-center rounded-full border-4 border-white bg-accent text-white shadow-xl md:rotate-0"
    >
      <svg className="h-9 w-9" viewBox="0 0 24 24" fill="none">
        <path
          d="M4 12h15m-6-6 6 6-6 6"
          stroke="currentColor"
          strokeWidth="2.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
