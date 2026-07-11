import { googleLoginUrl } from "./api.ts";
import { FlowLogo, MonoLabel } from "./ui.tsx";

const login = () => {
  window.location.href = googleLoginUrl();
};

export function LandingScreen() {
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
            <button onClick={login} className="hidden text-sm sm:block">
              Sign in
            </button>
            <button
              onClick={login}
              className="rounded-full bg-[#14181F] px-5 py-2.5 text-sm font-semibold text-white"
            >
              Start free
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
        <button
          onClick={login}
          className="mt-9 rounded-full bg-[#14181F] px-6 py-3.5 font-semibold text-white shadow-lg"
        >
          <span className="mr-2 inline-grid h-6 w-6 place-items-center rounded-full bg-white font-bold text-[#4285F4]">
            G
          </span>
          Continue with Google
        </button>
        <p className="mt-4 font-mono text-[11px] text-faint">
          Free tier · no card · 20 min of subtitles / month
        </p>
        <div className="mt-20 grid gap-5 text-left md:grid-cols-2">
          <VideoDemo label="01 · original">
            <p>Le campus ouvrira ses portes en 2027.</p>
          </VideoDemo>
          <VideoDemo label="02 · srt·flow" translated>
            <p>Le campus ouvrira ses portes en 2027.</p>
            <p className="text-[#F4CF86]">
              The campus will open its doors in 2027.
            </p>
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
            onClick={login}
            className="whitespace-nowrap text-lg font-semibold text-cyan-400"
          >
            Start free →
          </button>
        </div>
      </footer>
    </main>
  );
}

function VideoDemo({
  label,
  translated = false,
  children,
}: {
  label: string;
  translated?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2 flex justify-between font-mono text-[11px] text-faint">
        <span>{label}</span>
        <span>
          {translated ? "bilingual · read both at once" : "one language only"}
        </span>
      </div>
      <div
        className={`relative flex aspect-video flex-col items-center justify-end overflow-hidden rounded-2xl bg-[#090A0D] p-7 text-center text-sm text-white shadow-xl ${translated ? "ring-1 ring-accent" : ""}`}
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_35%,#293241_0%,transparent_55%)]" />
        <span className="relative mb-auto mt-auto text-3xl">▶</span>
        <div className="relative space-y-1">{children}</div>
        {translated && (
          <span className="absolute right-4 top-4 rounded-full bg-accent px-2.5 py-1 font-mono text-[10px] font-semibold text-white">
            FR + EN
          </span>
        )}
        <div
          className={`relative mt-4 h-1 w-full rounded-full ${translated ? "bg-accent" : "bg-white/30"}`}
        />
      </div>
    </div>
  );
}
