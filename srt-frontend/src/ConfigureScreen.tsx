import { useEffect, useState } from "react";

import {
  errMessage,
  getLanguages,
  getWorkers,
  type LanguageInfo,
  type PrepareResponse,
  type WorkerInfo,
} from "./api.ts";
import { CuesView } from "./CuesView.tsx";
import { ErrorBanner } from "./components.tsx";

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
}

export function ConfigureScreen({
  entries,
  onSourceChange,
  onRemove,
  onRetry,
  onProcess,
  onBack,
}: Props) {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [workerId, setWorkerId] = useState("");
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [targets, setTargets] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);

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
    setTargets((previous) => {
      const next = new Set(previous);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Configure batch</h2>
          <p className="text-sm text-slate-600">
            One worker and target set, with a source language per file.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-slate-600 underline"
        >
          start over
        </button>
      </div>

      {loadError && <ErrorBanner>{loadError}</ErrorBanner>}

      <div>
        <label className="mb-1 block text-sm font-medium">Worker</label>
        <select
          value={workerId}
          onChange={(event) => setWorkerId(event.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          {workers.length === 0 && <option value="">loading…</option>}
          {workers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} {item.healthy ? "" : "(unreachable)"}
            </option>
          ))}
        </select>
      </div>

      <div>
        <p className="mb-1 text-sm font-medium">Shared target languages</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {languages.map((language) => {
            const checked = targets.has(language.code);
            return (
              <label
                key={language.code}
                className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${checked ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-white"}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleTarget(language.code)}
                />
                {language.name}{" "}
                <span className="font-mono text-xs text-slate-500">
                  {language.code}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="space-y-3">
        {entries.map((entry) => {
          const effectiveTargets = [...targets].filter(
            (target) => target !== entry.sourceLang,
          );
          const noEffectiveTarget =
            entry.status === "ready" &&
            targets.size > 0 &&
            effectiveTargets.length === 0;
          return (
            <article
              key={entry.id}
              className="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{entry.name}</p>
                  {entry.status === "parsing" && (
                    <p className="text-sm text-slate-500">Parsing…</p>
                  )}
                  {entry.status === "error" && (
                    <p className="text-sm text-red-700">{entry.error}</p>
                  )}
                  {entry.prepare && (
                    <p className="text-xs text-slate-500">
                      {entry.prepare.count} cues · detected{" "}
                      {entry.prepare.detected_lang ?? "unknown"} (
                      {(entry.prepare.confidence * 100).toFixed(0)}%) ·{" "}
                      {effectiveTargets.length} effective targets
                    </p>
                  )}
                  {noEffectiveTarget && (
                    <p className="text-sm text-amber-700">
                      Skipped: no target remains after removing the source
                      language.
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  {entry.status === "error" && (
                    <button
                      type="button"
                      onClick={() => onRetry(entry.id)}
                      className="text-sm underline"
                    >
                      retry
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => onRemove(entry.id)}
                    className="text-sm text-slate-600 underline"
                  >
                    remove
                  </button>
                </div>
              </div>
              {entry.status === "ready" && entry.prepare && (
                <>
                  <label className="mt-3 block text-sm font-medium">
                    Source language
                    <select
                      value={entry.sourceLang ?? ""}
                      onChange={(event) =>
                        onSourceChange(entry.id, event.target.value)
                      }
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                    >
                      <option value="">(pick a source language)</option>
                      {languages.map((language) => (
                        <option key={language.code} value={language.code}>
                          {language.name} ({language.code})
                        </option>
                      ))}
                    </select>
                  </label>
                  <details className="mt-3">
                    <summary className="cursor-pointer text-sm text-slate-600">
                      preview parsed cues
                    </summary>
                    <CuesView
                      result={{
                        cues: entry.prepare.cues,
                        count: entry.prepare.count,
                      }}
                    />
                  </details>
                </>
              )}
            </article>
          );
        })}
      </div>

      <button
        type="button"
        disabled={disabled}
        onClick={() => onProcess(workerId, [...targets])}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {parsingCount > 0
          ? `Waiting for ${parsingCount} files to parse…`
          : `Process ${processable.length} files${skippedCount ? ` · ${skippedCount} skipped` : ""}`}
      </button>
    </section>
  );
}
