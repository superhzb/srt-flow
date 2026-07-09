import { useEffect, useState } from "react";

import {
  errMessage,
  listJobs,
  pollJob,
  type JobResult,
  type JobStatus,
  type JobSummary,
} from "./api.ts";
import { ErrorBanner, RefreshButton, SrtPreview } from "./components.tsx";
import { usePoll } from "./hooks.ts";

// History table from GET /api/jobs — the first thing persistence buys the
// user (PLAN.md slice 3). Clicking a row opens a detail panel that polls
// for live status while a job is in flight.
export function JobsScreen() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  function refresh() {
    listJobs()
      .then(setJobs)
      .catch((e: unknown) => setError(errMessage(e, "failed to load jobs")));
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <section className="mt-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Jobs</h2>
          <p className="text-sm text-slate-600">
            History of translation jobs (dev user).
          </p>
        </div>
        <RefreshButton onClick={refresh} />
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      {jobs === null && !error && (
        <p className="text-sm text-slate-600">Loading…</p>
      )}

      {jobs !== null && jobs.length === 0 && (
        <p className="text-sm text-slate-600">No jobs yet.</p>
      )}

      {jobs !== null && jobs.length > 0 && (
        <div className="overflow-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                <th className="px-3 py-2 text-left">job</th>
                <th className="px-3 py-2 text-left">status</th>
                <th className="px-3 py-2 text-left">worker</th>
                <th className="px-3 py-2 text-left">langs</th>
                <th className="px-3 py-2 text-left w-32">progress</th>
                <th className="px-3 py-2 text-left">created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const active = selectedId === j.id;
                return (
                  <tr
                    key={j.id}
                    tabIndex={0}
                    onClick={() => setSelectedId(j.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedId(j.id);
                      }
                    }}
                    className={`border-t border-slate-200 cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 hover:bg-slate-50 ${
                      active ? "bg-indigo-50" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {j.id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={j.status} />
                    </td>
                    <td className="px-3 py-2">{j.worker}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      <span className="text-slate-700">{j.src_lang}</span>
                      <span className="text-slate-400"> → </span>
                      {j.tgt_langs.join(", ")}
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {(j.progress * 100).toFixed(0)}%
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {new Date(j.created_at).toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedId && (
        <JobDetail jobId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  const tone =
    status === "done"
      ? "bg-emerald-100 text-emerald-800"
      : status === "failed"
        ? "bg-red-100 text-red-800"
        : status === "processing"
          ? "bg-indigo-100 text-indigo-800"
          : "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${tone}`}>
      {status}
    </span>
  );
}

function JobDetail({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { result: body, error } = usePoll(
    () => pollJob(jobId),
    (b) => b.status === "done" || b.status === "failed",
    { immediateFirst: true },
  );

  return (
    <div className="rounded-lg border border-slate-300 p-4 space-y-3 bg-white">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">
          Job <span className="font-mono text-sm">{jobId.slice(0, 8)}</span>
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-slate-500 hover:text-slate-800"
        >
          close
        </button>
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {body && (
        <>
          <div className="text-sm text-slate-700 space-y-1">
            <div>
              status: <StatusBadge status={body.status} />
            </div>
            <div>progress: {(body.progress * 100).toFixed(0)}%</div>
            <div>
              worker: <span className="font-mono">{body.worker}</span>
            </div>
            <div>
              langs:{" "}
              <span className="font-mono">
                {body.src_lang} → {body.tgt_langs.join(", ")}
              </span>
            </div>
            {body.error && (
              <div className="text-red-700">error: {body.error}</div>
            )}
          </div>
          {body.results && body.results.length > 0 && (
            <ResultsList results={body.results} />
          )}
        </>
      )}
    </div>
  );
}

function ResultsList({ results }: { results: JobResult[] }) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-slate-700">Outputs:</p>
      <ul className="text-sm space-y-1">
        {results.map((r) => (
          <li key={r.lang} className="flex items-center gap-2">
            <span className="font-mono text-xs w-12">{r.lang}</span>
            <a
              href={r.download_url}
              download
              className="text-indigo-600 hover:underline text-sm"
            >
              download
            </a>
            <SrtPreview url={r.download_url} />
          </li>
        ))}
      </ul>
    </div>
  );
}
