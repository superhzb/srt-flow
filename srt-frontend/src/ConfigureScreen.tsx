import { useEffect, useState } from "react";

import {
  errMessage,
  getLanguages,
  getWorkers,
  type LanguageInfo,
  type PrepareResponse,
  type WorkerInfo,
} from "./api.ts";
import { ErrorBanner, LanguagePill } from "./components.tsx";
import { langMeta } from "./languages.ts";
import { Select } from "./ui.tsx";

const MAX_TARGETS = 3;

export interface FileEntry {
  id: string;
  file: File;
  name: string;
  status: "parsing" | "ready" | "error";
  generation: number;
  prepare?: PrepareResponse;
  sourceLang?: string;
  error?: string;
}

interface Props {
  entries: FileEntry[];
  onSourceChange: (id: string, sourceLang: string) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  onProcess: (workerId: string, targets: string[]) => void;
  onBack: () => void;
  readOnly?: boolean;
}

export function ConfigureScreen({
  entries,
  onSourceChange,
  onRemove,
  onRetry,
  onProcess,
  onBack,
  readOnly = false,
}: Props) {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [workerId, setWorkerId] = useState("");
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [targets, setTargets] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getWorkers()
      .then((items) => {
        if (cancelled) return;
        setWorkers(items);
        const first = items.find((item) => item.healthy) ?? items[0];
        if (first) setWorkerId(first.id);
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setLoadError(errMessage(error, "failed to load workers"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workerId) return;
    let cancelled = false;
    setLanguages([]);
    setTargets(new Set());
    getLanguages(workerId)
      .then((items) => {
        if (!cancelled) setLanguages(items);
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setLoadError(errMessage(error, "failed to load languages"));
      });
    return () => {
      cancelled = true;
    };
  }, [workerId]);

  const parsingCount = entries.filter(
    (entry) => entry.status === "parsing",
  ).length;
  const processable = entries.filter(
    (entry) =>
      entry.status === "ready" &&
      Boolean(entry.sourceLang) &&
      [...targets].some((target) => target !== entry.sourceLang),
  );
  const skippedCount = entries.filter(
    (entry) =>
      entry.status === "ready" &&
      Boolean(entry.sourceLang) &&
      targets.size > 0 &&
      ![...targets].some((target) => target !== entry.sourceLang),
  ).length;
  const worker = workers.find((item) => item.id === workerId);
  const disabled =
    parsingCount > 0 ||
    processable.length === 0 ||
    targets.size === 0 ||
    !workerId ||
    (worker !== undefined && !worker.healthy);

  function toggleTarget(code: string) {
    if (readOnly) return;
    setTargets((previous) => {
      const next = new Set(previous);
      if (next.has(code)) {
        next.delete(code);
        setSelectionMessage(null);
      } else if (next.size >= MAX_TARGETS) {
        setSelectionMessage(`Choose up to ${MAX_TARGETS} target languages.`);
        return previous;
      } else {
        next.add(code);
        setSelectionMessage(null);
      }
      return next;
    });
  }

  const visibleLanguages = languages.filter((language) =>
    `${language.name} ${langMeta(language.code).native} ${language.code}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  const sourceCount = new Set(
    entries.map((entry) => entry.sourceLang).filter(Boolean),
  ).size;
  const totalTracks = entries.reduce(
    (count, entry) =>
      count +
      [...targets].filter((target) => target !== entry.sourceLang).length,
    0,
  );

  return (
    <section className="space-y-7 rise">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="font-mono text-[11px] uppercase tracking-[.14em] text-faint">
          {entries.length} {entries.length === 1 ? "file" : "files"} ·{" "}
          {sourceCount} source {sourceCount === 1 ? "language" : "languages"}{" "}
          detected
        </p>
        <button
          type="button"
          onClick={onBack}
          className="font-mono text-[11px] text-faint underline"
        >
          clear all
        </button>
      </div>

      {loadError && <ErrorBanner>{loadError}</ErrorBanner>}

      <div className="grid gap-2 sm:grid-cols-2">
        {entries.map((entry) => {
          const effectiveTargets = [...targets].filter(
            (target) => target !== entry.sourceLang,
          );
          const noEffectiveTarget =
            entry.status === "ready" &&
            targets.size > 0 &&
            effectiveTargets.length === 0;
          return (
            <div
              key={entry.id}
              className="rounded-xl border border-border bg-surface p-3.5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <span className="shrink-0 rounded-md bg-accent px-1.5 py-1 font-mono text-[10px] font-bold text-white">
                    SRT
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{entry.name}</p>
                    {entry.status === "parsing" && (
                      <p className="text-sm text-faint">Parsing…</p>
                    )}
                    {entry.status === "error" && (
                      <p className="text-sm text-red-700">{entry.error}</p>
                    )}
                    {entry.prepare && (
                      <p className="text-xs text-faint">
                        {entry.prepare.count} cues ·{" "}
                        {entry.sourceLang ?? "unknown"} source
                      </p>
                    )}
                    {noEffectiveTarget && (
                      <p className="text-sm text-amber-700">
                        Skipped: no target remains after removing the source
                        language.
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  {entry.status === "error" && (
                    <button
                      type="button"
                      disabled={readOnly}
                      onClick={() => onRetry(entry.id)}
                      className="text-sm underline"
                    >
                      retry
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={readOnly}
                    onClick={() => onRemove(entry.id)}
                    className="text-sm text-ink-muted underline"
                  >
                    remove
                  </button>
                </div>
              </div>
              {entry.status === "ready" && entry.prepare && (
                <label className="mt-3 block text-xs font-medium text-ink-muted">
                  Source language
                  <Select
                    value={entry.sourceLang ?? ""}
                    disabled={readOnly}
                    onChange={(event) =>
                      onSourceChange(entry.id, event.target.value)
                    }
                    className="mt-1 text-sm"
                  >
                    <option value="">(pick a source language)</option>
                    {languages.map((language) => (
                      <option key={language.code} value={language.code}>
                        {language.name} ({language.code})
                      </option>
                    ))}
                  </Select>
                </label>
              )}
            </div>
          );
        })}
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">Choose target languages</h2>
            <p className="mt-1 text-sm text-ink-muted">
              Select up to {MAX_TARGETS} languages for every uploaded file.
            </p>
          </div>
          <label className="min-w-56 text-xs font-medium text-ink-muted">
            Translation worker
            <Select
              value={workerId}
              disabled={readOnly}
              onChange={(event) => setWorkerId(event.target.value)}
              className="mt-1 text-sm"
            >
              {workers.length === 0 && <option value="">loading…</option>}
              {workers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} {item.healthy ? "" : "(unreachable)"}
                </option>
              ))}
            </Select>
          </label>
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-ink-muted">
            <b className="text-accent-deep">{targets.size}</b> of {MAX_TARGETS}{" "}
            selected
          </p>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search languages…"
            aria-label="Search languages"
            disabled={readOnly}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm sm:w-64"
          />
        </div>
        {selectionMessage && (
          <p role="status" className="mt-2 text-sm text-amber-700">
            {selectionMessage}
          </p>
        )}
        <div className="mt-4 flex max-h-64 flex-wrap gap-2 overflow-auto">
          {visibleLanguages.map((language) => {
            const checked = targets.has(language.code);
            const limitReached = targets.size >= MAX_TARGETS && !checked;
            return (
              <LanguagePill
                key={language.code}
                code={language.code}
                selected={checked}
                showCheck
                interactive
                disabled={readOnly || limitReached}
                onClick={() => toggleTarget(language.code)}
              />
            );
          })}
        </div>
      </div>

      <div className="flex justify-center pt-1">
        <button
          type="button"
          disabled={disabled || readOnly}
          onClick={() => onProcess(workerId, [...targets])}
          className="inline-flex items-center gap-2 rounded-xl bg-accent px-7 py-3.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {readOnly
            ? "Run settings locked"
            : parsingCount > 0
              ? `Waiting for ${parsingCount} files to parse…`
              : `⚡ Translate ${totalTracks} subtitle ${totalTracks === 1 ? "track" : "tracks"}${skippedCount ? ` · ${skippedCount} skipped` : ""} →`}
        </button>
      </div>
    </section>
  );
}
