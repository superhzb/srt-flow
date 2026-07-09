// Shared UI components extracted from repeated screen fragments.

import { useState } from "react";

import { useJobOutput } from "./hooks.ts";

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
      : "border-slate-200 bg-slate-50 text-slate-700";
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
      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {loading ? "Refreshing..." : children}
    </button>
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
        className="text-xs text-slate-500 hover:text-slate-800"
      >
        {open ? "hide" : label}
      </button>
      {open && error !== null && (
        <p className="text-xs text-red-700 mt-1">{error}</p>
      )}
      {open && error === null && text === null && (
        <p className="text-xs text-slate-500 mt-1">loading…</p>
      )}
      {open && text !== null && (
        <pre className="mt-1 bg-slate-900 text-slate-100 p-2 rounded text-xs overflow-auto max-h-48">
          {text}
        </pre>
      )}
    </div>
  );
}
