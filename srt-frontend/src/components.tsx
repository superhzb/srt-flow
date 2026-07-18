// Shared UI components extracted from repeated screen fragments.

import { useState } from "react";

import { useJobOutput } from "./hooks.ts";
import { langMeta } from "./languages.ts";

/**
 * Universal language chip: flag + English name + native name.
 * Single design shared by the picker (ConfigureScreen), the home
 * languages section (LandingScreen) and anywhere else a language is shown.
 */
export function LanguagePill({
  code,
  selected = false,
  showCheck = false,
  interactive = false,
  disabled = false,
  onClick,
}: {
  code: string;
  selected?: boolean;
  showCheck?: boolean;
  interactive?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}) {
  const { flag, en, native } = langMeta(code);
  const cls = `inline-flex select-none items-center gap-[7px] rounded-[10px] border px-3 py-2 text-[13px] transition ${
    selected
      ? "border-accent bg-accent-soft font-semibold text-accent-deep"
      : "border-border bg-surface font-medium text-ink-muted"
  } ${
    disabled
      ? "cursor-not-allowed opacity-45"
      : interactive
        ? "cursor-pointer hover:border-accent"
        : "cursor-default hover:-translate-y-0.5 hover:border-accent hover:bg-accent-soft hover:text-accent-deep"
  }`;
  const inner = (
    <>
      <span aria-hidden="true">{flag}</span>
      <span>{en}</span>
      {native !== en && (
        <span className="font-normal opacity-55">{native}</span>
      )}
      {showCheck && (
        <span
          aria-hidden="true"
          className="font-bold text-accent transition-opacity"
          style={{ opacity: selected ? 1 : 0 }}
        >
          ✓
        </span>
      )}
    </>
  );
  if (!interactive) return <span className={cls}>{inner}</span>;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      aria-pressed={selected}
      className={cls}
    >
      {inner}
    </button>
  );
}

/** Red error banner (duplicated ~8× before). `role="alert"` for a11y (#25). */
export function ErrorBanner({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"
    >
      {children}
    </div>
  );
}

/**
 * Tier pill. Previously defined twice with different styling
 * (AuthScreen vs BillingScreen); one canonical (bordered) style now.
 */
export function TierBadge({ tier }: { tier: "free" | "paid" }) {
  const classes =
    tier === "paid"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-border bg-surface-subtle text-ink-muted";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${classes}`}
    >
      {tier}
    </span>
  );
}

/** The Refresh button repeated across screens, with a loading-disabled state. */
export function RefreshButton({
  onClick,
  loading,
  children = "Refresh",
}: {
  onClick: () => void;
  loading?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-60"
    >
      {loading ? "Refreshing..." : children}
    </button>
  );
}

/** Shared credit usage meter. Used by History (free monthly) and Billing (total). */
export function QuotaBar({
  used,
  limit,
  label = "Free",
  ariaLabel = "Monthly free credits remaining",
}: {
  used: number;
  limit: number;
  label?: string;
  ariaLabel?: string;
}) {
  const remaining = Math.min(limit, Math.max(0, limit - used));
  const percent =
    limit > 0 ? Math.min(100, Math.max(0, (remaining / limit) * 100)) : 0;
  return (
    <div>
      <div className="mb-1.5 flex justify-between font-mono text-[10.5px] text-faint">
        <span>
          {label} · {remaining}/{limit} min
        </span>
        <span>{Math.round(percent)}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={ariaLabel}
        aria-valuemin={0}
        aria-valuemax={limit}
        aria-valuenow={remaining}
        className="h-1.5 overflow-hidden rounded-full bg-surface-inset"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent to-info"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Toggle-on .srt preview. Dedupes the fetch-on-toggle logic that lived in both
 * ResultsScreen (ResultPanel) and JobsScreen (PreviewButton): lazily fetches
 * the .srt text on first open, caches it, and renders a dark <pre>.
 */
export function SrtPreview({
  url,
  label = "preview",
}: {
  url: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const { text, error } = useJobOutput(url, open);

  return (
    <div className="ml-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs text-faint hover:text-ink"
      >
        {open ? "hide" : label}
      </button>
      {open && error !== null && (
        <p className="text-xs text-red-700 mt-1">{error}</p>
      )}
      {open && error === null && text === null && (
        <p className="text-xs text-faint mt-1">loading…</p>
      )}
      {open && text !== null && (
        <pre className="mt-1 bg-[#090a0d] text-white p-2 rounded text-xs overflow-auto max-h-48">
          {text}
        </pre>
      )}
    </div>
  );
}
