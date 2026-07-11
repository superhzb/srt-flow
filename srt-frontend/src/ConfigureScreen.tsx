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
import {
  Button,
  Card,
  Input,
  MonoLabel,
  SectionHeader,
  Select,
} from "./ui.tsx";

const REGIONS: Record<string, string> = {
  en: "🇺🇸",
  fr: "🇫🇷",
  es: "🇪🇸",
  de: "🇩🇪",
  it: "🇮🇹",
  pt: "🇵🇹",
  ja: "🇯🇵",
  ko: "🇰🇷",
  zh: "🇨🇳",
  ar: "🇸🇦",
  hi: "🇮🇳",
  ru: "🇷🇺",
  nl: "🇳🇱",
  pl: "🇵🇱",
  tr: "🇹🇷",
};
const NATIVE_NAMES: Record<string, string> = {
  en: "English",
  fr: "Français",
  es: "Español",
  de: "Deutsch",
  it: "Italiano",
  pt: "Português",
  ja: "日本語",
  ko: "한국어",
  zh: "中文",
  ar: "العربية",
  hi: "हिन्दी",
  ru: "Русский",
  nl: "Nederlands",
  pl: "Polski",
  tr: "Türkçe",
  uk: "Українська",
};
const RECENTS_KEY = "srtflow.recentLangs";

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
  const [recents, setRecents] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(RECENTS_KEY) ?? "[]") as string[];
    } catch {
      return [];
    }
  });

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
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
    setRecents((current) => {
      const next = [code, ...current.filter((x) => x !== code)].slice(0, 8);
      try {
        localStorage.setItem(RECENTS_KEY, JSON.stringify(next));
      } catch {
        /* unavailable */
      }
      return next;
    });
  }

  const visibleLanguages = languages.filter((language) =>
    `${language.name} ${NATIVE_NAMES[language.code] ?? ""} ${language.code}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  return (
    <section className="mt-6 space-y-6 rise">
      <div className="flex items-center justify-between">
        <div>
          <SectionHeader
            index="Step 2 / 4"
            title="Target languages"
            detail="One target set, a detected source for every file."
          />
          <p className="sr-only">
            One worker and target set, with a source language per file.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-ink-muted underline"
        >
          start over
        </button>
      </div>

      {loadError && <ErrorBanner>{loadError}</ErrorBanner>}

      <div>
        <label className="mb-1 block text-sm font-medium">Worker</label>
        <Select
          value={workerId}
          disabled={readOnly}
          onChange={(event) => setWorkerId(event.target.value)}
        >
          {workers.length === 0 && <option value="">loading…</option>}
          {workers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} {item.healthy ? "" : "(unreachable)"}
            </option>
          ))}
        </Select>
      </div>

      <div>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Shared target languages</p>
            <MonoLabel>{targets.size} selected</MonoLabel>
          </div>
          <Input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search languages…"
            aria-label="Search languages"
            className="max-w-xs"
            disabled={readOnly}
          />
        </div>
        {!query && recents.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <MonoLabel>recent</MonoLabel>
            {recents.map((code) => {
              const l = languages.find((x) => x.code === code);
              return l ? (
                <button
                  type="button"
                  disabled={readOnly}
                  key={code}
                  onClick={() => toggleTarget(code)}
                  className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs"
                >
                  {REGIONS[code] ?? code.toUpperCase()} {l.name}
                  {NATIVE_NAMES[code] && NATIVE_NAMES[code] !== l.name
                    ? ` · ${NATIVE_NAMES[code]}`
                    : ""}
                </button>
              ) : null;
            })}
          </div>
        )}
        <div className="grid max-h-72 grid-cols-2 gap-2 overflow-auto rounded-xl bg-surface-inset p-2 sm:grid-cols-3">
          {visibleLanguages.map((language) => {
            const checked = targets.has(language.code);
            return (
              <label
                key={language.code}
                className={`flex items-center gap-2 rounded-full border px-3 py-2 text-sm ${readOnly ? "cursor-default opacity-75" : "cursor-pointer"} ${checked ? "border-accent bg-accent-soft" : "border-border bg-surface"}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={readOnly}
                  onChange={() => toggleTarget(language.code)}
                />
                <span aria-hidden="true">
                  {REGIONS[language.code] ?? language.code.toUpperCase()}
                </span>
                <span className="min-w-0">
                  <span>{language.name}</span>
                  {NATIVE_NAMES[language.code] &&
                    NATIVE_NAMES[language.code] !== language.name && (
                      <span className="ml-1 text-xs text-ink-muted">
                        {NATIVE_NAMES[language.code]}
                      </span>
                    )}
                </span>
                {checked && (
                  <span className="ml-auto text-accent-deep" aria-hidden="true">
                    ✓
                  </span>
                )}
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
            <Card key={entry.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{entry.name}</p>
                  {entry.status === "parsing" && (
                    <p className="text-sm text-faint">Parsing…</p>
                  )}
                  {entry.status === "error" && (
                    <p className="text-sm text-red-700">{entry.error}</p>
                  )}
                  {entry.prepare && (
                    <p className="text-xs text-faint">
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
                <>
                  <label className="mt-3 block text-sm font-medium">
                    Source language
                    <Select
                      value={entry.sourceLang ?? ""}
                      disabled={readOnly}
                      onChange={(event) =>
                        onSourceChange(entry.id, event.target.value)
                      }
                      className="mt-1"
                    >
                      <option value="">(pick a source language)</option>
                      {languages.map((language) => (
                        <option key={language.code} value={language.code}>
                          {language.name} ({language.code})
                        </option>
                      ))}
                    </Select>
                  </label>
                  <details className="mt-3">
                    <summary className="cursor-pointer text-sm text-ink-muted">
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
            </Card>
          );
        })}
      </div>

      <Button
        type="button"
        disabled={disabled || readOnly}
        onClick={() => onProcess(workerId, [...targets])}
      >
        {readOnly
          ? "Run settings locked"
          : parsingCount > 0
            ? `Waiting for ${parsingCount} files to parse…`
            : `Process ${processable.length} files${skippedCount ? ` · ${skippedCount} skipped` : ""}`}
      </Button>
    </section>
  );
}
