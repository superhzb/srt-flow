import { useEffect, useRef } from "react";
import { pollJob, type JobStatusResponse } from "./api.ts";
import { usePoll } from "./hooks.ts";
import { langMeta } from "./languages.ts";
import { Card, MonoLabel, SectionHeader } from "./ui.tsx";

export function ProcessingScreen({
  jobs,
  onJobTerminal,
  complete,
  hasResults,
  onViewResults,
  onStartOver,
}: {
  jobs: { jobId: string; name: string }[];
  onJobTerminal: (jobId: string, result: JobStatusResponse) => void;
  complete: boolean;
  hasResults: boolean;
  onViewResults: () => void;
  onStartOver: () => void;
}) {
  const completionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!complete) return;
    requestAnimationFrame(() =>
      completionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      }),
    );
  }, [complete]);
  return (
    <section className="mt-6 space-y-5 rise">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <SectionHeader
          index="Step 3 / 3"
          title={complete ? "Translation complete" : "Translations are flowing"}
          detail={
            complete
              ? "Open History to review, arrange, and download the result."
              : "You can leave—your jobs keep running safely in the background."
          }
        />
        <MonoLabel>{jobs.length} jobs queued</MonoLabel>
      </div>
      <div className="space-y-3">
        {jobs.map((j) => (
          <JobProgress key={j.jobId} {...j} onTerminal={onJobTerminal} />
        ))}
      </div>
      {complete && (
        <div ref={completionRef} className="flex justify-center rise">
          <button
            type="button"
            onClick={hasResults ? onViewResults : onStartOver}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-7 py-3.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)]"
          >
            {hasResults
              ? "View results in History →"
              : "Start a new translation"}
          </button>
        </div>
      )}
    </section>
  );
}
function JobProgress({
  jobId,
  name,
  onTerminal,
}: {
  jobId: string;
  name: string;
  onTerminal: (jobId: string, result: JobStatusResponse) => void;
}) {
  const emitted = useRef(false);
  const { result, error, terminal } = usePoll(
    () => pollJob(jobId),
    (x) => x.status === "done" || x.status === "failed",
    { immediateFirst: true },
  );
  useEffect(() => {
    if (terminal && result && !emitted.current) {
      emitted.current = true;
      onTerminal(jobId, result);
    }
  }, [jobId, result, terminal, onTerminal]);
  const pct = Math.round((result?.progress ?? 0) * 100);
  const flowing = !terminal;
  return (
    <Card className="p-4">
      <div className="flex justify-between gap-3">
        <div>
          <p className="font-medium">{name}</p>
          <p className="font-mono text-[11px] text-faint">
            {result?.status ?? "connecting"} · {formatEta(result)}
          </p>
        </div>
        <strong className="font-mono text-sm text-accent-deep">{pct}%</strong>
      </div>
      <div
        role="progressbar"
        aria-label={`${name} progress`}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="mt-3 h-2 overflow-hidden rounded-full bg-surface-inset"
      >
        <div
          className="flow-progress h-full rounded-full transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      {result?.targets && result.targets.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
          <span
            className={`${flowing ? "language-flow" : ""} inline-flex items-center gap-1 rounded-full bg-surface-subtle px-2.5 py-1`}
          >
            <span aria-hidden="true">{langMeta(result.src_lang).flag}</span>
            <span>{langMeta(result.src_lang).en}</span>
            <span className="font-mono text-[10px] uppercase">source</span>
          </span>
          <span aria-hidden="true">→</span>
          {result.targets.map((target, index) => (
            <span
              key={target.lang}
              className={`${flowing ? "language-flow" : ""} inline-flex items-center gap-1 rounded-full bg-surface-subtle px-2.5 py-1`}
              style={{ animationDelay: `${index * 180}ms` }}
            >
              <span aria-hidden="true">{langMeta(target.lang).flag}</span>
              <span>{langMeta(target.lang).en}</span>
              <span className="font-mono text-[10px] uppercase">
                {target.status}
              </span>
            </span>
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </Card>
  );
}
function formatEta(job?: JobStatusResponse | null) {
  if (!job || job.eta_seconds == null) return "estimating…";
  if (job.eta_seconds < 60) return `about ${Math.ceil(job.eta_seconds)}s left`;
  return `about ${Math.ceil(job.eta_seconds / 60)}m left`;
}
