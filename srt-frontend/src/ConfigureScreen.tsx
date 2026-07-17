import { useEffect, useRef, useState, type Ref } from "react";

import {
  errMessage,
  getBillingBalance,
  getLanguages,
  getWorkers,
  type BillingBalance,
  type LanguageInfo,
  type PrepareResponse,
  type WorkerInfo,
} from "./api.ts";
import { ErrorBanner, LanguagePill } from "./components.tsx";
import { DEMO_LANGUAGES } from "./demoFixtures.ts";
import {
  billedCreditMinutes,
  formatDuration,
  sourceCreditMinutes,
  sourceDurationMs,
} from "./sourceMetrics.ts";
import { Button, SectionHeader, Select } from "./ui.tsx";

const MAX_TARGETS = 3;

// Pick the worker to default to from whatever /api/workers registered (driven
// by the backend's LLM_BACKENDS): prefer the first healthy one, otherwise the
// first registered. Returns "" when no workers are available.
function defaultWorkerId(workers: WorkerInfo[]): string {
  return (workers.find((worker) => worker.healthy) ?? workers[0])?.id ?? "";
}

export interface FileEntry {
  id: string;
  file: File;
  name: string;
  status: "parsing" | "ready" | "error";
  generation: number;
  prepare?: PrepareResponse;
  sourceLang?: string;
  sourceLine?: number;
  error?: string;
}

interface Props {
  entries: FileEntry[];
  onSourceChange: (id: string, sourceLang: string, sourceLine?: number) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  onProcess: () => void;
  onBack: () => void;
  guest?: boolean;
  targets: string[];
  onTargetsChange: (targets: string[]) => void;
  worker: string;
  onWorkerChange: (worker: string) => void;
  translateButtonRef?: Ref<HTMLButtonElement>;
  readOnly?: boolean;
}

export function ConfigureScreen({
  entries,
  onSourceChange,
  onRemove,
  onRetry,
  onProcess,
  onBack,
  guest = false,
  targets: targetValues,
  onTargetsChange,
  worker,
  onWorkerChange,
  translateButtonRef,
  readOnly = false,
}: Props) {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [languages, setLanguages] = useState<LanguageInfo[]>(
    guest ? DEMO_LANGUAGES : [],
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);
  const [balance, setBalance] = useState<BillingBalance | null | undefined>(
    guest ? null : undefined,
  );
  const [balanceError, setBalanceError] = useState<string | null>(null);
  const workerRef = useRef(worker);
  workerRef.current = worker;
  const onWorkerChangeRef = useRef(onWorkerChange);
  onWorkerChangeRef.current = onWorkerChange;

  useEffect(() => {
    if (guest) {
      setBalance(null);
      setBalanceError(null);
      return;
    }
    let cancelled = false;
    setBalance(undefined);
    setBalanceError(null);
    getBillingBalance()
      .then((value) => {
        if (!cancelled) setBalance(value);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setBalance(null);
          setBalanceError(errMessage(error, "failed to load credit balance"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [guest]);

  useEffect(() => {
    if (guest) return;
    let cancelled = false;
    getWorkers()
      .then((items) => {
        if (cancelled) return;
        setWorkers(items);
        // Auto-select the worker the backend registered from LLM_BACKENDS.
        // Keep a restored selection if it's still registered; otherwise take
        // the default (first healthy, else first).
        const selected = items.some((item) => item.id === workerRef.current)
          ? workerRef.current
          : defaultWorkerId(items);
        if (selected && selected !== workerRef.current) {
          onWorkerChangeRef.current(selected);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setLoadError(errMessage(error, "failed to load workers"));
      });
    return () => {
      cancelled = true;
    };
  }, [guest]);

  useEffect(() => {
    if (guest) {
      setLanguages(DEMO_LANGUAGES);
      setLoadError(null);
      return;
    }
    if (!worker) return;
    let cancelled = false;
    getLanguages(worker)
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
  }, [guest, worker]);

  const targets = new Set(targetValues);

  const carriedLanguage = (entry: FileEntry): string | undefined => {
    const langs = entry.prepare?.bilingual?.line_langs;
    return langs && entry.sourceLine !== undefined
      ? langs[1 - entry.sourceLine]
      : undefined;
  };
  const effectiveTargets = (entry: FileEntry): string[] => {
    const carried = carriedLanguage(entry);
    return [...targets].filter(
      (target) => target !== entry.sourceLang && target !== carried,
    );
  };

  const parsingCount = entries.filter(
    (entry) => entry.status === "parsing",
  ).length;
  const processable = entries.filter(
    (entry) =>
      entry.status === "ready" &&
      Boolean(entry.sourceLang) &&
      effectiveTargets(entry).length > 0,
  );
  const skippedCount = entries.filter(
    (entry) =>
      entry.status === "ready" &&
      Boolean(entry.sourceLang) &&
      targets.size > 0 &&
      effectiveTargets(entry).length === 0,
  ).length;
  const selectedWorker = workers.find((item) => item.id === worker);
  // Billed = source minutes × target languages per file (option A pricing).
  // Drop the source language so the count matches the backend's dedup.
  const creditMinutes = processable.reduce((total, entry) => {
    const langs = effectiveTargets(entry).length;
    return total + billedCreditMinutes(entry.prepare!.cues, langs);
  }, 0);
  const quotaExceeded = Boolean(
    balance && creditMinutes > balance.available_minutes,
  );
  const creditUnavailable = !guest && !balance;
  const disabled =
    parsingCount > 0 ||
    processable.length === 0 ||
    targets.size === 0 ||
    creditUnavailable ||
    quotaExceeded ||
    (!guest && !selectedWorker?.healthy);

  function toggleTarget(code: string) {
    if (readOnly) return;
    {
      const next = new Set(targets);
      if (next.has(code)) {
        next.delete(code);
        setSelectionMessage(null);
      } else if (next.size >= MAX_TARGETS) {
        setSelectionMessage(`Choose up to ${MAX_TARGETS} target languages.`);
        return;
      } else {
        next.add(code);
        setSelectionMessage(null);
      }
      onTargetsChange([...next]);
    }
  }

  const sourceLanguages = new Set(
    entries.map((entry) => entry.sourceLang).filter(Boolean),
  );
  const carriedLanguages = new Set(
    entries
      .map(carriedLanguage)
      .filter((lang): lang is string => Boolean(lang)),
  );
  const sourceCount = sourceLanguages.size;
  const totalTracks = entries.reduce(
    (count, entry) => count + effectiveTargets(entry).length,
    0,
  );

  return (
    <section className="space-y-7 rise">
      <SectionHeader
        index="Step 2 / 3"
        title="Choose languages"
        detail="Review the detected source and select up to three targets."
      />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="font-mono text-[11px] uppercase tracking-[.14em] text-faint">
          {entries.length} {entries.length === 1 ? "file" : "files"} ·{" "}
          {sourceCount} source {sourceCount === 1 ? "language" : "languages"}{" "}
          detected
        </p>
        <Button
          type="button"
          onClick={onBack}
          variant="danger"
          className="px-3 py-1.5"
        >
          Clear all files
        </Button>
      </div>

      {loadError && <ErrorBanner>{loadError}</ErrorBanner>}

      <div className="grid gap-2 sm:grid-cols-2">
        {entries.map((entry) => {
          const newTargets = effectiveTargets(entry);
          const noEffectiveTarget =
            entry.status === "ready" &&
            targets.size > 0 &&
            newTargets.length === 0;
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
                        {entry.prepare.count} lines ·{" "}
                        {formatDuration(sourceDurationMs(entry.prepare.cues))}{" "}
                        duration ·{" "}
                        {newTargets.length > 0 ? (
                          <>
                            {sourceCreditMinutes(entry.prepare.cues)} min ×{" "}
                            {newTargets.length}{" "}
                            {newTargets.length === 1 ? "language" : "languages"}{" "}
                            ={" "}
                            {billedCreditMinutes(
                              entry.prepare.cues,
                              newTargets.length,
                            )}{" "}
                            credit minutes
                          </>
                        ) : (
                          <>
                            {sourceCreditMinutes(entry.prepare.cues)} credit{" "}
                            {sourceCreditMinutes(entry.prepare.cues) === 1
                              ? "minute"
                              : "minutes"}
                            /language
                          </>
                        )}
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
              {entry.status === "ready" && entry.prepare?.bilingual ? (
                <fieldset className="mt-3 rounded-lg border border-border-subtle p-3">
                  <legend className="px-1 text-xs font-medium text-ink-muted">
                    This file already contains 2 languages
                  </legend>
                  <p className="mb-2 text-xs text-faint">
                    Choose which line to translate. The other language is kept
                    and is not charged.
                  </p>
                  <div className="space-y-2">
                    {entry.prepare.bilingual.line_langs.map((code, line) => {
                      const language = languages.find(
                        (item) => item.code === code,
                      );
                      return (
                        <label
                          key={`${code}-${line}`}
                          className="flex items-center gap-2 text-sm"
                        >
                          <input
                            type="radio"
                            name={`source-line-${entry.id}`}
                            checked={entry.sourceLine === line}
                            disabled={readOnly}
                            onChange={() =>
                              onSourceChange(entry.id, code, line)
                            }
                          />
                          Line {line + 1}: {language?.name ?? code} ({code})
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
              ) : entry.status === "ready" && entry.prepare ? (
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
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="rounded-2xl border border-border bg-surface p-5 shadow-sm sm:p-6">
        <div>
          <h2 className="text-lg font-semibold">Choose target languages</h2>
          <p className="mt-1 text-sm text-ink-muted">
            Select up to {MAX_TARGETS} languages for every uploaded file.
          </p>
        </div>
        <p className="mt-5 text-sm text-ink-muted">
          <b className="text-accent-deep">{targets.size}</b> of {MAX_TARGETS}{" "}
          selected
        </p>
        {selectionMessage && (
          <p role="status" className="mt-2 text-sm text-amber-700">
            {selectionMessage}
          </p>
        )}
        <div className="mt-4 flex max-h-64 flex-wrap gap-2 overflow-auto">
          {languages.map((language) => {
            const checked = targets.has(language.code);
            const limitReached = targets.size >= MAX_TARGETS && !checked;
            const isOnlySource =
              sourceLanguages.size === 1 && sourceLanguages.has(language.code);
            const isCarried = carriedLanguages.has(language.code);
            return (
              <LanguagePill
                key={language.code}
                code={language.code}
                selected={checked}
                showCheck
                interactive
                disabled={readOnly || limitReached || isOnlySource || isCarried}
                onClick={() => toggleTarget(language.code)}
              />
            );
          })}
        </div>
        <div className="mt-6 border-t border-border-subtle pt-5 text-center">
          {!guest && balance && (
            <p className="mb-3 text-sm text-ink-muted">
              This batch uses <b className="text-ink">{creditMinutes}</b> of{" "}
              <b className="text-ink">{balance.available_minutes}</b> available
              credit minutes.
            </p>
          )}
          <button
            ref={translateButtonRef}
            type="button"
            disabled={disabled || readOnly}
            onClick={onProcess}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-7 py-3.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)] disabled:cursor-not-allowed disabled:opacity-45"
          >
            {readOnly
              ? "Run settings locked"
              : parsingCount > 0
                ? `Waiting for ${parsingCount} files to parse…`
                : `⚡ Translate ${totalTracks} subtitle ${totalTracks === 1 ? "track" : "tracks"}${skippedCount ? ` · ${skippedCount} skipped` : ""} →`}
          </button>
        </div>
      </div>

      {balanceError && <ErrorBanner>{balanceError}</ErrorBanner>}
      {quotaExceeded && balance && (
        <ErrorBanner>
          This batch needs {creditMinutes} credit minutes, but only{" "}
          {balance.available_minutes} are available. Remove a file or add credit
          before translating.
        </ErrorBanner>
      )}
    </section>
  );
}
