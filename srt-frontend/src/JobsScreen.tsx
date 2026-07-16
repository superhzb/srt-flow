import { useEffect, useMemo, useState } from "react";

import {
  errMessage,
  listJobs,
  pollJob,
  type JobStatus,
  type JobSummary,
} from "./api.ts";
import { ErrorBanner } from "./components.tsx";
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
  const [languageOrderHost, setLanguageOrderHost] =
    useState<HTMLDivElement | null>(null);
  const poll = usePoll(
    listJobs,
    (items) =>
      items.every((job) => job.status === "done" || job.status === "failed"),
    { immediateFirst: true },
  );

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
      [
        job.filename,
        job.id,
        job.src_lang,
        ...(job.carried_langs ?? []),
        ...job.tgt_langs,
      ]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(needle)),
    );
  }, [jobs, query]);

  return (
    <section className="rise">
      {error && <ErrorBanner>{error}</ErrorBanner>}

      <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-5">
          <aside className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
            <h1 className="border-b border-border-subtle px-5 py-4 text-base font-semibold tracking-tight">
              History
            </h1>
            <label className="flex items-center gap-2 border-b border-border-subtle bg-surface-subtle px-4 py-3">
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

            <div className="flow-scroll max-h-[520px] min-h-40 overflow-y-auto bg-surface-subtle">
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
              {jobs !== null &&
                jobs.length > 0 &&
                filteredJobs.length === 0 && (
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
          <div ref={setLanguageOrderHost} />
        </div>

        <div className="min-w-0">
          {selectedId ? (
            <JobReview
              key={selectedId}
              jobId={selectedId}
              historySidebar={languageOrderHost}
            />
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
  const [languageOrderHost, setLanguageOrderHost] =
    useState<HTMLDivElement | null>(null);
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
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-5">
          <aside className="overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
            <h1 className="border-b border-border-subtle px-5 py-4 text-base font-semibold tracking-tight">
              History
            </h1>
            <div className="flow-scroll max-h-[520px] min-h-40 overflow-y-auto bg-surface-subtle">
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
                  className={`block w-full border-b border-border-subtle border-l-[3px] px-4 py-3.5 text-left ${selectedId === entry.id ? "border-l-accent bg-accent-soft/70" : "border-l-transparent bg-transparent hover:bg-surface"}`}
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
          <div ref={setLanguageOrderHost} />
        </div>
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
              historySidebar={languageOrderHost}
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
      className={`block w-full border-b border-border-subtle border-l-[3px] px-4 py-3.5 text-left outline-none ${active ? "border-l-accent bg-accent-soft/70" : "border-l-transparent bg-transparent hover:bg-surface"}`}
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

function JobReview({
  jobId,
  historySidebar,
}: {
  jobId: string;
  historySidebar: HTMLElement | null;
}) {
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
          carriedLangs={job.carried_langs ?? []}
          targetLangs={job.tgt_langs.filter(
            (target) => target !== job.src_lang,
          )}
          historyHeader={{ filename: job.filename ?? job.id.slice(0, 8), meta }}
          historySidebar={historySidebar}
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
