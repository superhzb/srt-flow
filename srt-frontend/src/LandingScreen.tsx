import { googleLoginUrl } from "./api.ts";
import { DEMO_LINE, LANG_LABEL } from "./demoLine.ts";
import { detectTargetLang } from "./lib.ts";
import { FlowLogo, MonoLabel } from "./ui.tsx";
import cockpit from "./assets/cockpit.webp";

const login = () => {
  window.location.href = googleLoginUrl();
};

export function LandingScreen({
  signedIn = false,
  onOpenApp,
}: {
  signedIn?: boolean;
  onOpenApp?: () => void;
} = {}) {
  const target = detectTargetLang();
  const primaryAction = signedIn && onOpenApp ? onOpenApp : login;
  return (
    <main className="min-h-screen bg-surface text-ink">
      <nav className="sticky top-0 z-20 border-b border-border/70 bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-5 px-5 py-4">
          <FlowLogo />
          <div className="hidden items-center gap-7 text-sm md:flex">
            <a href="#howitworks">How it works</a>
            <a href="#languages">Languages</a>
            <a href="#pricing">Pricing</a>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={primaryAction} className="hidden text-sm sm:block">
              {signedIn ? "Open app" : "Sign in"}
            </button>
            <button
              onClick={primaryAction}
              className="rounded-full bg-[#14181F] px-5 py-2.5 text-sm font-semibold text-white"
            >
              {signedIn ? "Workspace" : "Start free"}
            </button>
          </div>
        </div>
      </nav>
      <section className="mx-auto max-w-6xl px-5 pb-24 pt-16 text-center sm:pt-24">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface-subtle px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-ink-muted">
          <span className="pulse-dot h-2 w-2 rounded-full bg-accent" />
          100+ languages · auto-detected source
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
            onClick={primaryAction}
            className="inline-flex items-center justify-center gap-3 rounded-full bg-[#14181F] px-6 py-3.5 font-semibold text-white shadow-lg"
          >
            {!signedIn && <GoogleIcon />}
            {signedIn ? "Open workspace" : "Continue with Google"}
          </button>
          <button
            type="button"
            className="rounded-full border border-border bg-surface px-6 py-3.5 font-semibold text-ink shadow-sm transition hover:border-ink/30 hover:bg-surface-subtle"
          >
            Live demo
          </button>
        </div>
        <p className="mt-4 font-mono text-[11px] text-faint">
          Free tier · no card · 20 min of subtitles / month
        </p>
        <div className="relative mt-20 grid gap-12 text-left md:grid-cols-2 md:gap-8">
          <VideoDemo>
            <p>{DEMO_LINE.en}</p>
          </VideoDemo>
          <TransformationArrow />
          <VideoDemo badge={`EN + ${LANG_LABEL[target]}`}>
            {target !== "en" && (
              <p className="font-normal text-[#FFE066]">
                {DEMO_LINE[target]}
              </p>
            )}
            <p>{DEMO_LINE.en}</p>
          </VideoDemo>
        </div>
      </section>
      <section
        id="howitworks"
        className="scroll-mt-24 border-y border-border bg-surface-subtle px-5 py-24"
      >
        <div className="mx-auto max-w-6xl">
          <MonoLabel>three steps · zero friction</MonoLabel>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight">
            From upload to audience, without the busywork.
          </h2>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {[
              [
                "01",
                "Drop your SRT",
                "One file or a whole season. Source language is detected automatically.",
              ],
              [
                "02",
                "Pick your audience",
                "Search and select every language your audience speaks.",
              ],
              [
                "03",
                "Arrange & ship",
                "Preview, reorder, and download without translating again.",
              ],
            ].map(([n, t, d]) => (
              <article
                key={n}
                className="rounded-2xl border border-border bg-surface p-7 shadow-sm"
              >
                <span className="font-mono text-sm font-semibold text-accent-deep">
                  {n}
                </span>
                <h3 className="mt-8 text-xl font-semibold">{t}</h3>
                <p className="mt-3 text-sm leading-6 text-ink-muted">{d}</p>
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
            Translate into 100+ languages, from English, Français and Español to
            中文, 日本語, 한국어 and العربية.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {[
              "English",
              "Français",
              "Español",
              "Deutsch",
              "Português",
              "中文",
              "日本語",
              "한국어",
              "العربية",
              "हिन्दी",
              "Italiano",
              "Türkçe",
            ].map((x) => (
              <span
                key={x}
                className="rounded-full border border-border bg-surface-subtle px-4 py-2 text-sm"
              >
                {x}
              </span>
            ))}
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
            Start free. Scale when your audience does.
          </h2>
          <p className="mt-4 text-ink-muted">
            20 subtitle minutes every month, with no card required.
          </p>
        </div>
      </section>
      <footer className="bg-[#14181F] px-5 py-20 text-white">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-8 sm:flex-row sm:items-center">
          <h2 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
            Your work deserves an audience in every language.
          </h2>
          <button
            onClick={primaryAction}
            className="whitespace-nowrap text-lg font-semibold text-cyan-400"
          >
            {signedIn ? "Open workspace →" : "Start free →"}
          </button>
        </div>
      </footer>
    </main>
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
          <span className="absolute right-4 top-4 rounded-full bg-accent px-2.5 py-1 font-mono text-[10px] font-semibold text-white">
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
