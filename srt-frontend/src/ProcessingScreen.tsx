import { useEffect, useState } from "react";

import { pollJob, type JobResult, type JobStatusResponse } from "./api.ts";
import { usePoll } from "./hooks.ts";

interface Props {
  fileName: string;
  workerLabel: string;
  sourceLang: string;
  targets: string[];
  jobId: string;
  onDone: (results: JobResult[]) => void;
  onError: (message: string) => void;
}

function isTerminal(body: JobStatusResponse) {
  return body.status === "done" || body.status === "failed";
}

export function ProcessingScreen({
  fileName,
  workerLabel,
  sourceLang,
  targets,
  jobId,
  onDone,
  onError,
}: Props) {
  const { result, error, terminal } = usePoll(() => pollJob(jobId), isTerminal);
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState("starting…");

  useEffect(() => {
    if (result) {
      setProgress(result.progress);
      if (result.status === "done") {
        setStatusLabel("done");
        setProgress(1);
      } else if (result.status === "failed") {
        setStatusLabel("failed");
      } else {
        setStatusLabel(
          result.status === "processing"
            ? `translating · ${(result.progress * 100).toFixed(0)}%`
            : "queued…",
        );
      }
    }
  }, [result]);

  // Fire the terminal callback exactly once.
  useEffect(() => {
    if (!terminal) return;
    if (error) {
      onError(error);
    } else if (result?.status === "done" && result.results) {
      onDone(result.results);
    } else if (result?.status === "failed") {
      onError(result.error ?? "translation failed");
    }
  }, [terminal, error, result, onDone, onError]);

  const pct = Math.round(progress * 100);

  return (
    <section className="mt-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Translating</h2>
        <p className="text-sm text-slate-600">
          <span className="font-medium">{fileName}</span> · {workerLabel} ·{" "}
          <span className="font-mono">{sourceLang}</span> →{" "}
          <span className="font-mono">{targets.join(", ")}</span>
        </p>
      </div>
      <div className="space-y-1">
        <div
          className="h-3 rounded-full bg-slate-200 overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label="translation progress"
        >
          <div
            className="h-full bg-indigo-600 transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-600">
          <span>{statusLabel}</span>
          <span className="tabular-nums">{pct}%</span>
        </div>
      </div>
    </section>
  );
}
