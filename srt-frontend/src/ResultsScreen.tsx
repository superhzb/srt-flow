import { useState } from "react";

import { type JobResult } from "./api.ts";
import { useJobOutput } from "./hooks.ts";

interface Props {
  jobId: string;
  results: JobResult[];
  onRestart: () => void;
  onViewJobs: () => void;
}

export function ResultsScreen({
  jobId,
  results,
  onRestart,
  onViewJobs,
}: Props) {
  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            Translated · {results.length}
          </h2>
          <p className="text-sm text-ink-muted">
            job <span className="font-mono">{jobId.slice(0, 8)}</span> · outputs
            saved
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onViewJobs}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle"
          >
            View jobs
          </button>
          <button
            type="button"
            onClick={onRestart}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle"
          >
            New translation
          </button>
        </div>
      </div>
      <div className="space-y-4">
        {results.map((r) => (
          <ResultPanel key={r.lang} jobId={jobId} result={r} />
        ))}
      </div>
    </section>
  );
}

function ResultPanel({ jobId, result }: { jobId: string; result: JobResult }) {
  const [showSrt, setShowSrt] = useState(false);
  const { text, error } = useJobOutput(result.download_url, showSrt);

  // Download is a plain anchor to the same download_url — the browser
  // streams the .srt attachment directly, no JS blob juggling needed.
  const baseName = jobId.slice(0, 8);

  return (
    <div className="rounded-lg border border-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-surface-subtle border-b border-border">
        <div>
          <span className="font-semibold">{result.lang}</span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm text-ink-muted">
            <input
              type="checkbox"
              checked={showSrt}
              onChange={(e) => setShowSrt(e.target.checked)}
            />
            raw .srt
          </label>
          <a
            href={result.download_url}
            download={`${baseName}.${result.lang}.srt`}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:bg-accent-soft0"
          >
            Download
          </a>
        </div>
      </div>
      {showSrt ? (
        error ? (
          <div className="p-4 text-sm text-red-700">Error: {error}</div>
        ) : text === null ? (
          <div className="p-4 text-sm text-faint">Loading…</div>
        ) : (
          <pre className="bg-[#090a0d] text-white p-4 overflow-auto text-xs max-h-96">
            {text}
          </pre>
        )
      ) : (
        <div className="p-4 text-sm text-ink-muted">
          output saved · toggle raw .srt to preview.
        </div>
      )}
    </div>
  );
}
