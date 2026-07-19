// Static content pages: Privacy Policy, Terms, Contact, About. Each is a
// stateless, prerendered prose page sharing one shell (header + footer). They
// dispatch off the pathname the same way lang routes do (see routes.ts,
// main.tsx, prerender-entry.tsx). Kept in sync with docs/legal/*.md.
//
// This is a route module by design: it colocates the page components with the
// matchContentRoute() dispatcher, so the fast-refresh "only export components"
// rule (a dev-HMR nicety) does not apply here.
/* eslint-disable react-refresh/only-export-components */

import { useEffect, type ReactNode } from "react";

import {
  LEGAL_JURISDICTION,
  LEGAL_NAME,
  LEGAL_UPDATED,
  SUPPORT_EMAIL,
} from "./legal.ts";
import { LegalLinks } from "./LegalLinks.tsx";
import {
  ABOUT_META,
  CONTACT_META,
  PRIVACY_META,
  TERMS_META,
  setMeta,
  type PageMeta,
} from "./seo.ts";
import { FlowLogo } from "./ui.tsx";

function StaticPageShell({
  meta,
  children,
}: {
  meta: PageMeta;
  children: ReactNode;
}) {
  useEffect(() => {
    setMeta(meta);
  }, [meta]);

  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="border-b border-border/70 bg-surface/90">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-4">
          <a href="/" aria-label="srt-flow home">
            <FlowLogo />
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-16">{children}</main>

      <footer className="mt-8 bg-[#14181F] px-5 py-12 text-white">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          <LegalLinks />
        </div>
      </footer>
    </div>
  );
}

// Shared prose helpers — keep the styling consistent across pages.
function H1({ children }: { children: ReactNode }) {
  return (
    <h1 className="text-4xl font-semibold leading-tight tracking-[-.03em]">
      {children}
    </h1>
  );
}
function H2({ children }: { children: ReactNode }) {
  return <h2 className="mt-12 text-2xl font-semibold">{children}</h2>;
}
function P({ children }: { children: ReactNode }) {
  return (
    <p className="mt-4 text-base leading-relaxed text-ink-muted">{children}</p>
  );
}
function Updated() {
  return (
    <p className="mt-3 text-sm text-faint">Last updated: {LEGAL_UPDATED}</p>
  );
}
function MailLink() {
  return (
    <a
      href={`mailto:${SUPPORT_EMAIL}`}
      className="font-medium text-accent-deep underline underline-offset-4"
    >
      {SUPPORT_EMAIL}
    </a>
  );
}

function PrivacyPage() {
  return (
    <StaticPageShell meta={PRIVACY_META}>
      <H1>Privacy Policy</H1>
      <Updated />
      <P>
        srt-flow (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;the Service&rdquo;)
        is operated as a sole proprietorship by <strong>{LEGAL_NAME}</strong>,
        located in <strong>{LEGAL_JURISDICTION}</strong>. This policy explains
        what personal information we collect, why, who we share it with, and
        your rights. For any privacy question or request, contact <MailLink />.
        This is also our designated privacy contact under Quebec&rsquo;s Law 25.
      </P>

      <H2>1. What we collect</H2>
      <ul className="mt-4 list-disc space-y-2 pl-6 text-base text-ink-muted">
        <li>Email address and Google subject ID (via Google sign-in).</li>
        <li>IP address (security, rate-limiting, abuse prevention).</li>
        <li>
          Uploaded subtitle (<code>.srt</code>) files, their text, and the
          translation output.
        </li>
        <li>Payment records and credit balance (via Stripe).</li>
        <li>
          First-party analytics identifiers (<code>anon_id</code>,{" "}
          <code>session_id</code>) and usage events.
        </li>
      </ul>
      <P>
        We do <strong>not</strong> collect passwords (sign-in is Google OAuth
        only) and use <strong>no</strong> third-party advertising or analytics
        trackers.
      </P>

      <H2>2. Card payments</H2>
      <P>
        Card details are collected and processed by <strong>Stripe</strong>. We
        never see or store your full card number.
      </P>

      <H2>3. How your subtitle text is processed — please read</H2>
      <P>
        To translate your file, the subtitle{" "}
        <strong>text you upload is sent to our LLM provider, DeepSeek</strong> (
        <code>api.deepseek.com</code>, operated from China).
      </P>
      <ul className="mt-4 list-disc space-y-2 pl-6 text-base text-ink-muted">
        <li>
          DeepSeek may use submitted text to train and improve its models.
        </li>
        <li>
          Your subtitle text therefore leaves our systems, is transferred to a
          provider in China, and may be retained and used by that provider.
        </li>
        <li>
          <strong>
            Do not upload subtitle files containing sensitive, confidential, or
            personal information
          </strong>{" "}
          you are not comfortable sharing under these terms.
        </li>
        <li>
          China has no data-protection adequacy decision under the GDPR or
          Quebec Law 25. By uploading, you consent to this cross-border transfer
          as necessary to provide the Service you request. If you are an
          EU/UK/EEA user and do not consent, do not upload files.
        </li>
      </ul>

      <H2>4. Sub-processors</H2>
      <ul className="mt-4 list-disc space-y-2 pl-6 text-base text-ink-muted">
        <li>
          <strong>Google</strong> — sign-in / identity (USA).
        </li>
        <li>
          <strong>Stripe</strong> — payments (USA / global).
        </li>
        <li>
          <strong>DeepSeek</strong> — LLM translation (China).
        </li>
        <li>
          <strong>Cloudflare</strong> — network / email routing (global).
        </li>
      </ul>

      <H2>5. Retention</H2>
      <P>
        Uploaded files and translation output are deleted automatically 30 days
        after the job is created; you may request earlier deletion at any time.
        Analytics event identity fields are scrubbed at 365 days. Account and
        billing records are retained while your account exists and as required
        by tax/accounting law.
      </P>

      <H2>6. Your rights</H2>
      <P>
        Depending on where you live (PIPEDA, Quebec Law 25, GDPR, CCPA) you may
        access, correct, delete, or port your personal information, and withdraw
        consent. To delete your account and associated data, or exercise any
        other right, email <MailLink />. We respond within the timeframe
        required by applicable law.
      </P>

      <H2>7. Cookies &amp; local storage</H2>
      <P>
        We use first-party local storage for an <code>anon_id</code> and{" "}
        <code>session_id</code> to measure product usage; when you sign in, the{" "}
        <code>anon_id</code> is associated with your account server-side. We use
        no third-party or advertising cookies. Sign-in uses a secure, HttpOnly
        session cookie required for the Service to function.
      </P>

      <H2>8. Security</H2>
      <P>
        Sign-in via Google OAuth (no passwords). Session cookies are HttpOnly,
        Secure, SameSite=lax. Uploads are size- and type-restricted with
        path-traversal guards.
      </P>

      <H2>9. Changes</H2>
      <P>
        We may update this policy; the &ldquo;last updated&rdquo; date will
        change and material changes will be surfaced in-app.
      </P>

      <H2>10. Contact</H2>
      <P>
        <MailLink /> — {LEGAL_JURISDICTION}.
      </P>
    </StaticPageShell>
  );
}

function TermsPage() {
  return (
    <StaticPageShell meta={TERMS_META}>
      <H1>Terms of Service</H1>
      <Updated />
      <P>
        These Terms govern your use of srt-flow (&ldquo;the Service&rdquo;),
        operated as a sole proprietorship by <strong>{LEGAL_NAME}</strong> in{" "}
        <strong>{LEGAL_JURISDICTION}</strong>. By using the Service you agree to
        these Terms. If you do not agree, do not use the Service.
      </P>

      <H2>1. The Service</H2>
      <P>
        srt-flow translates uploaded <code>.srt</code> subtitle files into other
        languages using an automated LLM translation provider. Translations are
        machine-generated and may contain errors.
      </P>

      <H2>2. Accounts</H2>
      <P>
        You sign in with Google and are responsible for activity under your
        account. You must be old enough to form a binding contract in your
        jurisdiction.
      </P>

      <H2>3. Acceptable use</H2>
      <P>
        You agree not to upload content you do not have the right to translate.{" "}
        <strong>
          You warrant that you own or are licensed to use the subtitle files you
          upload.
        </strong>{" "}
        Subtitles are often copyrighted; rights are your responsibility, not
        ours. You further agree not to upload unlawful, infringing, or malicious
        content, or to abuse, overload, reverse-engineer, or attempt to break
        the Service or its rate limits. We may suspend or terminate accounts
        that violate these Terms.
      </P>

      <H2>4. Third-party processing</H2>
      <P>
        To translate your files, subtitle text is sent to our LLM provider{" "}
        <strong>DeepSeek</strong> (operated from China), which may use it to
        train its models. See our{" "}
        <a
          href="/privacy/"
          className="text-accent-deep underline underline-offset-4"
        >
          Privacy Policy
        </a>
        . By uploading, you accept this processing.
      </P>

      <H2>5. Credits, billing &amp; refunds</H2>
      <P>
        The Service uses prepaid credits (translation minutes) purchased via
        Stripe as one-time payments — no subscription or auto-renewal. A free
        tier of 30 minutes/month is provided without a card.{" "}
        <strong>
          Unused credits are refundable within 30 days of purchase;
          used/consumed credits are non-refundable.
        </strong>{" "}
        Refunds are processed manually via Stripe — email <MailLink />. Prices
        are shown in USD; your bank may apply currency-conversion charges.
      </P>

      <H2>6. Intellectual property</H2>
      <P>
        You retain rights to the files you upload and the translations you
        receive. You grant us the limited right to process your files solely to
        provide the Service.
      </P>

      <H2>7. Disclaimer</H2>
      <P>
        THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS
        AVAILABLE&rdquo;, WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED,
        INCLUDING FITNESS FOR A PARTICULAR PURPOSE AND ACCURACY OF TRANSLATIONS.
        We do not warrant uninterrupted or error-free service.
      </P>

      <H2>8. Limitation of liability</H2>
      <P>
        To the maximum extent permitted by law, our total liability for any
        claim arising from the Service is limited to the greater of (a) the
        amount you paid us in the 90 days before the claim, or (b) CAD $50. We
        are not liable for indirect, incidental, or consequential damages.
      </P>

      <H2>9. Termination</H2>
      <P>
        You may stop using the Service and request account deletion at any time
        (<MailLink />
        ). We may suspend or terminate access for breach of these Terms.
      </P>

      <H2>10. Governing law</H2>
      <P>
        These Terms are governed by the laws of the Province of Quebec and the
        federal laws of Canada applicable therein. Disputes are subject to the
        courts of Quebec.
      </P>

      <H2>11. Changes</H2>
      <P>
        We may update these Terms; the &ldquo;last updated&rdquo; date will
        change. Continued use after changes means you accept them.
      </P>

      <H2>12. Contact</H2>
      <P>
        <MailLink /> — {LEGAL_JURISDICTION}.
      </P>
    </StaticPageShell>
  );
}

function ContactPage() {
  return (
    <StaticPageShell meta={CONTACT_META}>
      <H1>Contact</H1>
      <P>
        Questions, help with a translation, billing, refunds, or a privacy
        request — we&rsquo;re a small team and read every message.
      </P>
      <div className="mt-8 rounded-2xl border border-border bg-surface-subtle p-6">
        <p className="font-mono text-[11px] uppercase tracking-wide text-faint">
          Support email
        </p>
        <p className="mt-3 text-lg">
          <MailLink />
        </p>
      </div>
      <P>
        For refund requests, include the email you signed in with and the
        approximate purchase date. For privacy requests (access or deletion of
        your data), email the same address — see our{" "}
        <a
          href="/privacy/"
          className="text-accent-deep underline underline-offset-4"
        >
          Privacy Policy
        </a>
        .
      </P>
      <P>srt-flow is operated from {LEGAL_JURISDICTION}.</P>
    </StaticPageShell>
  );
}

function AboutPage() {
  return (
    <StaticPageShell meta={ABOUT_META}>
      <H1>About srt-flow</H1>
      <P>
        srt-flow turns a subtitle file into a bilingual one. Upload an{" "}
        <code>.srt</code>, the source language is auto-detected, and you get
        broadcast-ready subtitles back in minutes — with the original and the
        translation stacked line by line.
      </P>
      <P>
        The idea is simple: learn a language from the videos you already love.
        Watching with both languages on screen turns passive viewing into
        practice, one line at a time.
      </P>
      <P>
        We keep it lightweight — no subscription, a free tier with no card, and
        one-time credit packs when you need more. srt-flow is an independent
        project operated from {LEGAL_JURISDICTION}.
      </P>
      <P>
        Questions or feedback? <MailLink />.
      </P>
      <div className="mt-10">
        <a
          href="/app"
          className="inline-flex items-center gap-3 rounded-full bg-[#14181F] px-6 py-3.5 font-semibold text-white shadow-lg transition hover:-translate-y-0.5 hover:bg-accent-deep hover:shadow-xl"
        >
          Try it free →
        </a>
      </div>
    </StaticPageShell>
  );
}

type ContentRoute = {
  path: string;
  meta: PageMeta;
  Component: () => ReactNode;
};

const CONTENT_ROUTE_TABLE: ContentRoute[] = [
  { path: "/privacy/", meta: PRIVACY_META, Component: PrivacyPage },
  { path: "/terms/", meta: TERMS_META, Component: TermsPage },
  { path: "/contact/", meta: CONTACT_META, Component: ContactPage },
  { path: "/about/", meta: ABOUT_META, Component: AboutPage },
];

// Path list for PUBLIC_ROUTES lives in routes.ts (CONTENT_ROUTES) to avoid a
// circular import; keep these paths and that list in sync.

/** Resolve a pathname to its content page, tolerating a missing trailing slash. */
export function matchContentRoute(pathname: string): ContentRoute | undefined {
  const normalized = pathname.endsWith("/") ? pathname : `${pathname}/`;
  return CONTENT_ROUTE_TABLE.find((r) => r.path === normalized);
}
