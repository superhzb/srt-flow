import { useEffect, useRef, useState } from "react";

import { errMessage, prepareSrt, startJob } from "./api.ts";
import { AuthScreen } from "./AuthScreen.tsx";
import { BillingScreen } from "./BillingScreen.tsx";
import { ConfigureScreen, type FileEntry } from "./ConfigureScreen.tsx";
import { DbScreen } from "./DbScreen.tsx";
import { ErrorBanner } from "./components.tsx";
import { JobsScreen } from "./JobsScreen.tsx";

type EnqueuedJob = { entry: FileEntry; jobId: string };
type EnqueueFailure = { entry: FileEntry; message: string };
type State =
  | { kind: "idle" }
  | { kind: "configure"; entries: FileEntry[] }
  | { kind: "enqueuing"; entries: FileEntry[] }
  | { kind: "enqueued"; jobs: EnqueuedJob[]; failures: EnqueueFailure[] };
type Tab = "upload" | "jobs" | "db" | "auth" | "billing";
type Theme = "light" | "dark";

const ACCEPT = ".srt";
export const MAX_BATCH = 20;

function initialTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".srt"))
    return "must have a .srt extension";
  if (file.size === 0) return "is empty";
  if (file.size > 4 * 1024 * 1024) return "exceeds the 4 MiB limit";
  return null;
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [tab, setTab] = useState<Tab>("upload");
  const [checkoutStatus, setCheckoutStatus] = useState<
    "success" | "cancel" | null
  >(null);
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* unavailable */
    }
  }, [theme]);

  useEffect(() => {
    const url = new URL(window.location.href);
    const checkout = url.searchParams.get("checkout");
    if (checkout !== "success" && checkout !== "cancel") return;
    setTab("billing");
    setCheckoutStatus(checkout);
    url.searchParams.delete("checkout");
    window.history.replaceState(
      {},
      "",
      `${url.pathname}${url.search}${url.hash}`,
    );
  }, []);

  function parseEntry(entry: FileEntry) {
    const generation = entry.generation;
    prepareSrt(entry.file)
      .then((prepare) => {
        setState((previous) => {
          if (previous.kind !== "configure") return previous;
          const current = previous.entries.find((item) => item.id === entry.id);
          if (
            !current ||
            current.status !== "parsing" ||
            current.generation !== generation
          )
            return previous;
          return {
            ...previous,
            entries: previous.entries.map((item) =>
              item.id === entry.id
                ? {
                    ...item,
                    status: "ready",
                    prepare,
                    sourceLang: prepare.detected_lang ?? "",
                    error: undefined,
                  }
                : item,
            ),
          };
        });
      })
      .catch((error: unknown) => {
        setState((previous) => {
          if (previous.kind !== "configure") return previous;
          const current = previous.entries.find((item) => item.id === entry.id);
          if (
            !current ||
            current.status !== "parsing" ||
            current.generation !== generation
          )
            return previous;
          return {
            ...previous,
            entries: previous.entries.map((item) =>
              item.id === entry.id
                ? {
                    ...item,
                    status: "error",
                    error: errMessage(error, "failed to parse file"),
                  }
                : item,
            ),
          };
        });
      });
  }

  function submit(files: File[]) {
    const entries = files.map<FileEntry>((file) => ({
      id: crypto.randomUUID(),
      file,
      name: file.name,
      status: "parsing",
      generation: 0,
    }));
    setState({ kind: "configure", entries });
    entries.forEach(parseEntry);
  }

  function updateEntries(change: (entries: FileEntry[]) => FileEntry[]) {
    setState((previous) =>
      previous.kind === "configure"
        ? { ...previous, entries: change(previous.entries) }
        : previous,
    );
  }

  function retry(id: string) {
    if (state.kind !== "configure") return;
    const current = state.entries.find((entry) => entry.id === id);
    if (!current) return;
    const retried: FileEntry = {
      ...current,
      status: "parsing",
      generation: current.generation + 1,
      error: undefined,
      prepare: undefined,
    };
    setState({
      ...state,
      entries: state.entries.map((entry) =>
        entry.id === id ? retried : entry,
      ),
    });
    parseEntry(retried);
  }

  async function handleProcess(worker: string, targets: string[]) {
    if (state.kind !== "configure") return;
    const entries = state.entries.filter(
      (entry) =>
        entry.status === "ready" &&
        entry.prepare &&
        entry.sourceLang &&
        targets.some((target) => target !== entry.sourceLang),
    );
    setState({ kind: "enqueuing", entries: state.entries });
    const jobs: EnqueuedJob[] = [];
    const failures: EnqueueFailure[] = [];
    for (let offset = 0; offset < entries.length; offset += 4) {
      const chunk = entries.slice(offset, offset + 4);
      const results = await Promise.allSettled(
        chunk.map((entry) =>
          startJob({
            cues: entry.prepare!.cues,
            sourceLang: entry.sourceLang!,
            targets,
            worker,
            filename: entry.name,
          }),
        ),
      );
      results.forEach((result, index) => {
        const entry = chunk[index];
        if (result.status === "fulfilled")
          jobs.push({ entry, jobId: result.value.job_id });
        else
          failures.push({
            entry,
            message: errMessage(result.reason, "failed to queue"),
          });
      });
    }
    setState({ kind: "enqueued", jobs, failures });
  }

  function restart() {
    setState({ kind: "idle" });
    setTab("upload");
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">srt-flow</h1>
            <p className="mt-1 text-sm text-slate-600">
              Translate one or many <code>.srt</code> files.
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              setTheme((value) => (value === "light" ? "dark" : "light"))
            }
            className="rounded-md border border-slate-300 bg-white p-2"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          >
            {theme === "light" ? "☾" : "☀"}
          </button>
        </header>
        <nav className="mb-6 flex gap-1 border-b border-slate-200">
          {(["upload", "jobs", "db", "auth", "billing"] as Tab[]).map(
            (item) => (
              <TabButton
                key={item}
                active={tab === item}
                onClick={() => setTab(item)}
              >
                {item[0].toUpperCase() + item.slice(1)}
              </TabButton>
            ),
          )}
        </nav>

        {tab === "jobs" && <JobsScreen />}
        {tab === "db" && <DbScreen />}
        {tab === "auth" && <AuthScreen />}
        {tab === "billing" && (
          <BillingScreen
            checkoutStatus={checkoutStatus}
            onCheckoutStatusHandled={() => setCheckoutStatus(null)}
          />
        )}
        {tab === "upload" && state.kind === "idle" && (
          <UploadFlow onSubmit={submit} />
        )}
        {tab === "upload" && state.kind === "configure" && (
          <ConfigureScreen
            entries={state.entries}
            onSourceChange={(id, sourceLang) =>
              updateEntries((entries) =>
                entries.map((entry) =>
                  entry.id === id ? { ...entry, sourceLang } : entry,
                ),
              )
            }
            onRemove={(id) =>
              updateEntries((entries) =>
                entries.filter((entry) => entry.id !== id),
              )
            }
            onRetry={retry}
            onProcess={handleProcess}
            onBack={restart}
          />
        )}
        {tab === "upload" && state.kind === "enqueuing" && (
          <p className="mt-6 text-sm text-slate-600">
            Queueing{" "}
            {state.entries.filter((entry) => entry.status === "ready").length}{" "}
            files…
          </p>
        )}
        {tab === "upload" && state.kind === "enqueued" && (
          <EnqueuedSummary
            jobs={state.jobs}
            failures={state.failures}
            onViewJobs={() => setTab("jobs")}
            onRestart={restart}
          />
        )}
      </div>
    </div>
  );
}

function EnqueuedSummary({
  jobs,
  failures,
  onViewJobs,
  onRestart,
}: {
  jobs: EnqueuedJob[];
  failures: EnqueueFailure[];
  onViewJobs: () => void;
  onRestart: () => void;
}) {
  return (
    <section className="mt-6 space-y-4">
      <h2 className="text-lg font-semibold">
        Queued {jobs.length} {jobs.length === 1 ? "job" : "jobs"}
      </h2>
      {failures.length > 0 && (
        <ErrorBanner>
          {failures.length} failed to queue:{" "}
          {failures
            .map((failure) => `${failure.entry.name}: ${failure.message}`)
            .join("; ")}
        </ErrorBanner>
      )}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onViewJobs}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"
        >
          View in Jobs
        </button>
        <button
          type="button"
          onClick={onRestart}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm"
        >
          Upload more
        </button>
      </div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`border-b-2 px-4 py-2 text-sm font-medium ${active ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-600"}`}
    >
      {children}
    </button>
  );
}

export function UploadFlow({
  onSubmit,
}: {
  onSubmit: (files: File[]) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function submit(selected: File[]) {
    const capped = selected.slice(0, MAX_BATCH);
    const accepted = capped.filter((file) => validateFile(file) === null);
    const rejected =
      capped.length -
      accepted.length +
      Math.max(0, selected.length - MAX_BATCH);
    setMessage(
      rejected > 0
        ? `${accepted.length} accepted, ${rejected} rejected${selected.length > MAX_BATCH ? ` (maximum ${MAX_BATCH} files)` : ""}.`
        : null,
    );
    if (accepted.length > 0) onSubmit(accepted);
  }

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop .srt files here, or activate to pick files"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          submit(Array.from(event.dataTransfer.files));
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center ${dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-white"}`}
      >
        <p className="font-medium">Drop up to {MAX_BATCH} .srt files here</p>
        <p className="mt-1 text-sm text-slate-500">or click to pick files</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(event) => {
            submit(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>
      {message && <ErrorBanner>{message}</ErrorBanner>}
    </>
  );
}
