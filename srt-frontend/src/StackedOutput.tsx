import { useEffect, useMemo, useState } from "react";

import { errMessage, fetchStackedOutput, stackedDownloadUrl } from "./api.ts";

interface StackedOutputProps {
  jobId: string;
  sourceLang: string;
  targetLangs: string[];
}

export function StackedOutput({
  jobId,
  sourceLang,
  targetLangs,
}: StackedOutputProps) {
  const languagesKey = [sourceLang, ...targetLangs].join("\u0000");
  const allLanguages = useMemo(
    () => [sourceLang, ...targetLangs],
    // languagesKey captures value changes without depending on array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [languagesKey],
  );
  const [orderedLanguages, setOrderedLanguages] = useState(allLanguages);
  const [included, setIncluded] = useState(() => new Set(allLanguages));
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestOrder = orderedLanguages.filter((lang) => included.has(lang));
  const orderKey = requestOrder.join(",");

  useEffect(() => {
    setOrderedLanguages(allLanguages);
    setIncluded(new Set(allLanguages));
  }, [allLanguages]);

  useEffect(() => {
    if (requestOrder.length === 0) {
      setPreview(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setError(null);
    setPreview(null);
    fetchStackedOutput(jobId, requestOrder)
      .then((text) => {
        if (!controller.signal.aborted) setPreview(text);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(errMessage(cause, "failed to load stacked preview"));
        }
      });
    return () => controller.abort();
    // orderKey is the stable representation of the derived request order.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, orderKey]);

  function move(index: number, delta: -1 | 1) {
    const nextIndex = index + delta;
    if (nextIndex < 0 || nextIndex >= orderedLanguages.length) return;
    setOrderedLanguages((current) => {
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  }

  function toggle(lang: string) {
    setIncluded((current) => {
      const next = new Set(current);
      if (next.has(lang)) next.delete(lang);
      else next.add(lang);
      return next;
    });
  }

  const downloadUrl =
    requestOrder.length > 0
      ? stackedDownloadUrl(jobId, requestOrder)
      : undefined;

  return (
    <section className="space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div>
        <h4 className="text-sm font-medium text-slate-800">Stacked output</h4>
        <p className="text-xs text-slate-600">
          Reorder or exclude languages before previewing and downloading.
        </p>
      </div>
      <ol className="space-y-1">
        {orderedLanguages.map((lang, index) => {
          const isIncluded = included.has(lang);
          return (
            <li key={lang} className="flex items-center gap-2">
              <span className="w-24 rounded bg-white px-2 py-1 font-mono text-xs">
                {lang}{" "}
                {lang === sourceLang && (
                  <span className="text-slate-400">src</span>
                )}
              </span>
              <button
                type="button"
                onClick={() => move(index, -1)}
                disabled={index === 0}
                aria-label={`Move ${lang} up`}
                className="rounded border px-2 disabled:opacity-40"
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => move(index, 1)}
                disabled={index === orderedLanguages.length - 1}
                aria-label={`Move ${lang} down`}
                className="rounded border px-2 disabled:opacity-40"
              >
                ↓
              </button>
              <button
                type="button"
                onClick={() => toggle(lang)}
                aria-pressed={isIncluded}
                className="text-xs text-indigo-700 hover:underline"
              >
                {isIncluded ? "exclude" : "include"}
              </button>
            </li>
          );
        })}
      </ol>
      {downloadUrl ? (
        <a
          href={downloadUrl}
          download
          className="inline-block text-sm text-indigo-600 hover:underline"
        >
          download stacked SRT
        </a>
      ) : (
        <span aria-disabled="true" className="text-sm text-slate-400">
          download stacked SRT
        </span>
      )}
      {requestOrder.length === 0 && (
        <p className="text-xs text-amber-700">Include at least one language.</p>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
      {requestOrder.length > 0 && !error && preview === null && (
        <p className="text-sm text-slate-500">Loading preview…</p>
      )}
      {preview !== null && (
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-white p-3 text-xs">
          {preview}
        </pre>
      )}
    </section>
  );
}
