import { useEffect, useMemo, useState } from "react";

import {
  errMessage,
  listJobs,
  pollJob,
  type JobStatus,
  type JobSummary,
} from "./api.ts";
import { ErrorBanner, RefreshButton } from "./components.tsx";
import { usePoll } from "./hooks.ts";
import { langMeta } from "./languages.ts";
import { StackedOutput } from "./StackedOutput.tsx";
import { listDemoEntries, type DemoHistoryEntry } from "./clientStorage.ts";

const MOCK_QUOTA = { used: 16, limit: 30 };

export function JobsScreen({ guest = false }: { guest?: boolean }) {
  return guest ? <GuestHistory /> : <RealJobsScreen />;
}

function RealJobsScreen() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const poll = usePoll(
    listJobs,
    (items) =>
      items.every((job) => job.status === "done" || job.status === "failed"),
    { immediateFirst: true },
  );

  function refresh() {
    setError(null);
    listJobs()
      .then(setJobs)
      .catch((e: unknown) => setError(errMessage(e, "failed to load jobs")));
  }

  useEffect(() => {
    if (poll.result) setJobs(poll.result);
    if (poll.error) setError(poll.error);
  }, [poll.result, poll.error]);

  useEffect(() => {
    if (!selectedId && jobs?.length) setSelectedId(jobs[0].id);
    if (selectedId && jobs && !jobs.some((job) => job.id === selectedId))
      setSelectedId(jobs[0]?.id ?? null);
  }, [jobs, selectedId]);

  const filteredJobs = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return jobs ?? [];
    return (jobs ?? []).filter((job) =>
      [job.filename, job.id, job.src_lang, ...job.tgt_langs]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(needle)),
    );
  }, [jobs, query]);

  return (
    <section className="rise">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-[-.03em]">History</h1>
          <p className="mt-2 text-[15px] text-ink-muted">
            Everything you&apos;ve translated. Re-arrange languages and
            re-download anytime — no re-translating, ever.
          </p>
        </div>
        <RefreshButton onClick={refresh} />
      </div>

      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
          <label className="flex items-center gap-2 border-b border-border-subtle px-4 py-3">
            <span aria-hidden="true" className="text-faint">
              ⌕
            </span>
            <span className="sr-only">Search history</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="search history"
              className="min-w-0 flex-1 border-0 bg-transparent font-mono text-[11px] text-ink outline-none placeholder:text-faint"
            />
          </label>

          <div className="flow-scroll max-h-[520px] min-h-40 overflow-y-auto">
            {jobs === null && !error && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                Loading…
              </p>
            )}
            {jobs?.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No jobs yet.
              </p>
            )}
            {jobs !== null && jobs.length > 0 && filteredJobs.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No matching jobs.
              </p>
            )}
            {filteredJobs.map((job) => (
              <JobListItem
                key={job.id}
                job={job}
                active={selectedId === job.id}
                onSelect={() => setSelectedId(job.id)}
              />
            ))}
          </div>

          <QuotaFooter />
        </aside>

        <div className="min-w-0">
          {selectedId ? (
            <JobReview key={selectedId} jobId={selectedId} />
          ) : (
            <div className="flex min-h-72 items-center justify-center rounded-2xl border border-border bg-surface p-8 text-center text-sm text-ink-muted">
              Select a job to review and download it.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function GuestHistory() {
  const [entries, setEntries] = useState<DemoHistoryEntry[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => {
    setError(null);
    listDemoEntries()
      .then((items) => {
        setEntries(items);
        setSelectedId((current) =>
          current && items.some((item) => item.id === current)
            ? current
            : (items[0]?.id ?? null),
        );
      })
      .catch((reason: unknown) =>
        setError(errMessage(reason, "failed to load demo history")),
      );
  };
  useEffect(refresh, []);
  const selected = entries?.find((entry) => entry.id === selectedId);
  return (
    <section className="rise">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 inline-flex rounded-full bg-accent-soft px-3 py-1 font-mono text-xs font-semibold text-accent-deep">
            Demo History · local only
          </div>
          <h1 className="text-3xl font-bold tracking-[-.03em]">History</h1>
          <p className="mt-2 text-[15px] text-ink-muted">
            Signed-out History contains only demo translations stored in this
            browser for 30 minutes.
          </p>
        </div>
        <RefreshButton onClick={refresh} />
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
          <div className="flow-scroll max-h-[520px] min-h-40 overflow-y-auto">
            {entries === null && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                Loading…
              </p>
            )}
            {entries?.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-ink-muted">
                No demo translations yet.
              </p>
            )}
            {entries?.map((entry) => (
              <button
                key={entry.id}
                type="button"
                onClick={() => setSelectedId(entry.id)}
                className={`block w-full border-b border-border-subtle border-l-[3px] px-4 py-3.5 text-left ${selectedId === entry.id ? "border-l-accent bg-accent-soft/50" : "border-l-transparent bg-surface"}`}
              >
                <span className="block truncate text-[13.5px] font-semibold">
                  {entry.filename}
                </span>
                <span className="mt-0.5 block font-mono text-[10.5px] text-faint">
                  Demo translation ·{" "}
                  {formatJobDate(new Date(entry.createdAt).toISOString())}
                </span>
              </button>
            ))}
          </div>
        </aside>
        <div className="min-w-0 overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
          {selected ? (
            <StackedOutput
              demoCues={selected.cuesByLanguage}
              sourceLang={selected.sourceLang}
              targetLangs={selected.targetLangs}
              historyHeader={{
                filename: selected.filename,
                meta: `Demo translation · ${formatJobDate(new Date(selected.createdAt).toISOString())}`,
              }}
            />
          ) : (
            <div className="flex min-h-72 items-center justify-center p-8 text-center text-sm text-ink-muted">
              Run the sample demo to create a local History entry.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function JobListItem({
  job,
  active,
  onSelect,
}: {
  job: JobSummary;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`block w-full border-b border-border-subtle border-l-[3px] px-4 py-3.5 text-left outline-none hover:bg-surface-subtle ${active ? "border-l-accent bg-accent-soft/50" : "border-l-transparent bg-surface"}`}
    >
      <span className="flex items-center gap-2.5">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-semibold">
            {job.filename ?? job.id.slice(0, 8)}
          </span>
          <span className="mt-0.5 block truncate font-mono text-[10.5px] text-faint">
            {formatJobDate(job.created_at)} ·{" "}
            <span aria-hidden="true">{langMeta(job.src_lang).flag}</span>{" "}
            {job.src_lang.toUpperCase()} → {job.tgt_langs.length}{" "}
            {job.tgt_langs.length === 1 ? "lang" : "langs"}
          </span>
        </span>
        <StatusBadge status={job.status} />
      </span>
    </button>
  );
}

function JobReview({ jobId }: { jobId: string }) {
  const { result: job, error } = usePoll(
    () => pollJob(jobId),
    (body) => body.status === "done" || body.status === "failed",
    { immediateFirst: true },
  );

  if (error) return <ErrorBanner>{error}</ErrorBanner>;
  if (!job)
    return (
      <div className="rounded-2xl border border-border bg-surface p-8 text-sm text-ink-muted">
        Loading job…
      </div>
    );

  const meta = `${formatJobDate(job.created_at)} · ${langMeta(job.src_lang).flag} ${job.src_lang.toUpperCase()} → ${job.tgt_langs.length} ${job.tgt_langs.length === 1 ? "language" : "languages"}`;
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_14px_34px_-26px_rgba(20,24,31,.2)]">
      {job.status === "done" ? (
        <StackedOutput
          jobId={jobId}
          sourceLang={job.src_lang}
          targetLangs={job.tgt_langs.filter(
            (target) => target !== job.src_lang,
          )}
          historyHeader={{ filename: job.filename ?? job.id.slice(0, 8), meta }}
        />
      ) : (
        <div className="p-6">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold">
              {job.filename ?? job.id.slice(0, 8)}
            </h2>
            <StatusBadge status={job.status} />
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            {job.error ?? `${(job.progress * 100).toFixed(0)}% complete`}
          </p>
        </div>
      )}
    </div>
  );
}

function QuotaFooter() {
  const percent = Math.round((MOCK_QUOTA.used / MOCK_QUOTA.limit) * 100);
  return (
    <div className="border-t border-border-subtle bg-surface-subtle px-4 py-3.5">
      <div className="mb-1.5 flex justify-between font-mono text-[10.5px] text-faint">
        <span>
          Free · {MOCK_QUOTA.used}/{MOCK_QUOTA.limit} min
        </span>
        <span>{percent}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-inset">
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent to-info"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  const tone =
    status === "done"
      ? "bg-emerald-100 text-emerald-800"
      : status === "failed"
        ? "bg-amber-100 text-amber-800"
        : status === "processing"
          ? "bg-accent-soft text-accent-deep"
          : "bg-surface-inset text-ink-muted";
  return (
    <span
      className={`shrink-0 rounded-md px-2 py-1 font-mono text-[10px] ${tone}`}
    >
      {status}
    </span>
  );
}

function formatJobDate(value: string): string {
  const date = new Date(value);
  const elapsed = Date.now() - date.getTime();
  if (elapsed >= 0 && elapsed < 60_000) return "Just now";
  if (elapsed >= 0 && elapsed < 3_600_000)
    return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed >= 0 && elapsed < 86_400_000)
    return `${Math.floor(elapsed / 3_600_000)}h ago`;
  if (elapsed >= 0 && elapsed < 172_800_000) return "Yesterday";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
