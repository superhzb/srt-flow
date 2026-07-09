import { useEffect, useState } from "react";

import {
  errMessage,
  getLanguages,
  getWorkers,
  type LanguageInfo,
  type PrepareResponse,
  type WorkerInfo,
} from "./api.ts";
import { ErrorBanner } from "./components.tsx";

interface Props {
  fileName: string;
  prepare: PrepareResponse;
  onProcess: (
    workerId: string,
    workerLabel: string,
    sourceLang: string,
    targets: string[],
  ) => void;
  onBack: () => void;
}

export function ConfigureScreen({
  fileName,
  prepare,
  onProcess,
  onBack,
}: Props) {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [workerId, setWorkerId] = useState<string>("");
  const [languages, setLanguages] = useState<LanguageInfo[]>([]);
  const [sourceLang, setSourceLang] = useState<string>(
    prepare.detected_lang ?? "",
  );
  const [targets, setTargets] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getWorkers()
      .then((ws) => {
        if (cancelled) return;
        setWorkers(ws);
        const firstHealthy = ws.find((w) => w.healthy);
        const first = firstHealthy ?? ws[0];
        if (first) setWorkerId(first.id);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setLoadError(errMessage(e, "failed to load workers"));
        }
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
      .then((langs) => {
        if (cancelled) return;
        setLanguages(langs);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setLoadError(errMessage(e, "failed to load languages"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workerId]);

  // When source changes, drop it from targets if it slipped in.
  useEffect(() => {
    setTargets((prev) => {
      if (!prev.has(sourceLang)) return prev;
      const next = new Set(prev);
      next.delete(sourceLang);
      return next;
    });
  }, [sourceLang]);

  function toggleTarget(code: string) {
    setTargets((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function handleProcess() {
    setProcessError(null);
    if (!workerId) {
      setProcessError("pick a worker");
      return;
    }
    if (!sourceLang) {
      setProcessError("pick a source language");
      return;
    }
    if (targets.size === 0) {
      setProcessError("pick at least one target language");
      return;
    }
    onProcess(workerId, worker?.label ?? workerId, sourceLang, [...targets]);
  }

  const worker = workers.find((w) => w.id === workerId);
  const workerBlocked = worker !== undefined && !worker.healthy;

  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Configure translation</h2>
          <p className="text-sm text-slate-600">
            <span className="font-medium">{fileName}</span> · {prepare.count}{" "}
            cues
            {prepare.detected_lang && (
              <>
                {" "}
                · detected:{" "}
                <span className="font-mono">{prepare.detected_lang}</span> (
                {(prepare.confidence * 100).toFixed(0)}%)
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-slate-600 hover:text-slate-900 underline"
        >
          pick another file
        </button>
      </div>

      {loadError && <ErrorBanner>{loadError}</ErrorBanner>}

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">
          Worker
        </label>
        <select
          value={workerId}
          onChange={(e) => setWorkerId(e.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          {workers.length === 0 && <option value="">loading…</option>}
          {workers.map((w) => (
            <option key={w.id} value={w.id}>
              {w.label} {w.healthy ? "" : "(unreachable)"}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">
          Source language
        </label>
        <select
          value={sourceLang}
          onChange={(e) => setSourceLang(e.target.value)}
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">(pick a source language)</option>
          {languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.name} ({l.code})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">
          Target languages
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {languages
            .filter((l) => l.code !== sourceLang)
            .map((l) => {
              const checked = targets.has(l.code);
              return (
                <label
                  key={l.code}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer ${
                    checked
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-slate-300 bg-white"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleTarget(l.code)}
                  />
                  <span>
                    {l.name}{" "}
                    <span className="text-slate-500 font-mono text-xs">
                      {l.code}
                    </span>
                  </span>
                </label>
              );
            })}
        </div>
      </div>

      {processError && <ErrorBanner>{processError}</ErrorBanner>}

      <button
        type="button"
        onClick={handleProcess}
        disabled={workerBlocked || targets.size === 0 || !sourceLang}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 hover:bg-indigo-500"
      >
        Process {targets.size > 0 && `(${targets.size})`}
      </button>
      {workerBlocked && (
        <p className="text-xs text-amber-700 mt-1">
          Selected worker is unreachable — start it or pick another.
        </p>
      )}
    </section>
  );
}
