import { useEffect, useRef, useState } from "react";

import { pollJob, type JobResult } from "./api.ts";

interface Props {
  fileName: string;
  workerLabel: string;
  sourceLang: string;
  targets: string[];
  jobId: string;
  onDone: (results: JobResult[]) => void;
  onError: (message: string) => void;
}

const POLL_INTERVAL_MS = 1500;

export function ProcessingScreen({
  fileName,
  workerLabel,
  sourceLang,
  targets,
  jobId,
  onDone,
  onError,
}: Props) {
  const [progress, setProgress] = useState(0);
  const [statusLabel, setStatusLabel] = useState("starting…");
  const finishedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      try {
        const body = await pollJob(jobId);
        if (cancelled || finishedRef.current) return;
        setProgress(body.progress);
        if (body.status === "done" && body.results) {
          finishedRef.current = true;
          setStatusLabel("done");
          setProgress(1);
          onDone(body.results);
          return;
        }
        if (body.status === "failed") {
          finishedRef.current = true;
          setStatusLabel("failed");
          onError(body.error ?? "translation failed");
          return;
        }
        setStatusLabel(
          body.status === "processing"
            ? `translating · ${(body.progress * 100).toFixed(0)}%`
            : "queued…",
        );
        timer = setTimeout(tick, POLL_INTERVAL_MS);
      } catch (e: unknown) {
        if (cancelled || finishedRef.current) return;
        finishedRef.current = true;
        onError(e instanceof Error ? e.message : "polling failed");
      }
    }

    timer = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, onDone, onError]);

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
        <div className="h-3 rounded-full bg-slate-200 overflow-hidden">
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
