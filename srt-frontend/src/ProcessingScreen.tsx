import { useEffect, useRef } from "react";
import { pollJob, type JobStatusResponse, type TargetProgress } from "./api.ts";
import { usePoll } from "./hooks.ts";
import { Card, MonoLabel, SectionHeader } from "./ui.tsx";

export function ProcessingScreen({
  jobs,
  onJobTerminal,
}: {
  jobs: { jobId: string; name: string }[];
  onJobTerminal: (jobId: string, result: JobStatusResponse) => void;
}) {
  return (
    <section className="mt-6 space-y-5 rise">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <SectionHeader
          index="Step 3 / 4"
          title="Translations are flowing"
          detail="You can leave—your jobs keep running safely in the background."
        />
        <MonoLabel>{jobs.length} jobs queued</MonoLabel>
      </div>
      <div className="space-y-3">
        {jobs.map((j) => (
          <JobProgress key={j.jobId} {...j} onTerminal={onJobTerminal} />
        ))}
      </div>
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
      {result?.targets && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {result.targets.map((t) => (
            <TargetRow key={t.lang} target={t} />
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </Card>
  );
}
function TargetRow({ target }: { target: TargetProgress }) {
  const pct = Math.round(target.progress * 100);
  return (
    <div className="rounded-lg bg-surface-subtle px-3 py-2">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${target.status === "done" ? "bg-ok" : target.status === "running" ? "bg-accent animate-pulse" : "bg-faint"}`}
        />
        <span className="font-mono text-xs uppercase">{target.lang}</span>
        <span className="ml-auto text-xs text-ink-muted">
          {target.status === "done"
            ? "done"
            : target.status === "running"
              ? `${pct}%`
              : "queued"}
        </span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-inset">
        <div
          className="flow-progress h-full rounded-full transition-[width]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
function formatEta(job?: JobStatusResponse | null) {
  if (!job || job.eta_seconds == null) return "estimating…";
  if (job.eta_seconds < 60) return `about ${Math.ceil(job.eta_seconds)}s left`;
  return `about ${Math.ceil(job.eta_seconds / 60)}m left`;
}
