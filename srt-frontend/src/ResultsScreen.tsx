import { useState } from "react";

import type { JobResult, PrepareResponse } from "./api.ts";

interface Props {
  fileName: string;
  prepare: PrepareResponse;
  results: JobResult[];
  onRestart: () => void;
}

export function ResultsScreen({ fileName, prepare, results, onRestart }: Props) {
  const baseName = fileName.replace(/\.srt$/i, "");
  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Translated · {results.length}</h2>
          <p className="text-sm text-slate-600">
            <span className="font-medium">{fileName}</span> · {prepare.count} cues
          </p>
        </div>
        <button
          type="button"
          onClick={onRestart}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
        >
          New translation
        </button>
      </div>
      <div className="space-y-4">
        {results.map((r) => (
          <ResultPanel key={r.lang} baseName={baseName} result={r} />
        ))}
      </div>
    </section>
  );
}

function ResultPanel({ baseName, result }: { baseName: string; result: JobResult }) {
  const [showSrt, setShowSrt] = useState(false);

  function download() {
    const blob = new Blob([result.srt], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${baseName}.${result.lang}.srt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
        <div>
          <span className="font-semibold">{result.lang}</span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={showSrt}
              onChange={(e) => setShowSrt(e.target.checked)}
            />
            raw .srt
          </label>
          <button
            type="button"
            onClick={download}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-500"
          >
            Download
          </button>
        </div>
      </div>
      {showSrt ? (
        <pre className="bg-slate-900 text-slate-100 p-4 overflow-auto text-xs max-h-96">
          {result.srt}
        </pre>
      ) : (
        <div className="p-4 text-sm text-slate-600">
          {result.srt.split("\n\n").length} cue blocks · toggle raw .srt to preview.
        </div>
      )}
    </div>
  );
}
