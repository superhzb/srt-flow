import { useCallback, useEffect, useRef, useState } from "react";

import {
  errMessage,
  getMe,
  prepareSrt,
  startJob,
  type JobStatusResponse,
  type Me,
} from "./api.ts";
import { AuthScreen } from "./AuthScreen.tsx";
import { BillingScreen } from "./BillingScreen.tsx";
import { ConfigureScreen, type FileEntry } from "./ConfigureScreen.tsx";
import { ErrorBanner } from "./components.tsx";
import { JobsScreen } from "./JobsScreen.tsx";
import { LandingScreen } from "./LandingScreen.tsx";
import { ProcessingScreen } from "./ProcessingScreen.tsx";
import { StackedOutput } from "./StackedOutput.tsx";
import { Button, Card, FlowLogo, SectionHeader } from "./ui.tsx";

type EnqueuedJob = { entry: FileEntry; jobId: string };
type EnqueueFailure = { entry: FileEntry; message: string };
type Stage = "idle" | "configure" | "enqueuing" | "enqueued";
type Workflow = {
  stage: Stage;
  entries: FileEntry[];
  worker: string;
  targets: string[];
  jobs: EnqueuedJob[];
  enqueueFailures: EnqueueFailure[];
  terminalJobs: Record<string, JobStatusResponse>;
};
type Tab = "translate" | "jobs" | "auth" | "billing";
type Theme = "light" | "dark";

const ACCEPT = ".srt";
const EMPTY_WORKFLOW: Workflow = {
  stage: "idle",
  entries: [],
  worker: "",
  targets: [],
  jobs: [],
  enqueueFailures: [],
  terminalJobs: {},
};
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
  const [session, setSession] = useState<Me | null | undefined>(undefined);
  const [workflow, setWorkflow] = useState<Workflow>(EMPTY_WORKFLOW);
  const [tab, setTab] = useState<Tab>("translate");
  const [showLanding, setShowLanding] = useState(false);
  const [checkoutStatus, setCheckoutStatus] = useState<
    "success" | "cancel" | null
  >(null);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const configureRef = useRef<HTMLElement>(null);
  const processingRef = useRef<HTMLElement>(null);
  const previewRef = useRef<HTMLElement>(null);
  const previousStage = useRef<Stage>("idle");
  const previewRevealed = useRef(false);

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
    let live = true;
    getMe()
      .then((me) => {
        if (!live) return;
        setSession(me);
        if (me && window.location.pathname === "/")
          window.history.replaceState({}, "", "/app");
        else if (!me && window.location.pathname === "/app")
          window.history.replaceState({}, "", "/");
      })
      .catch(() => {
        if (live) setSession(null);
      });
    return () => {
      live = false;
    };
  }, []);

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

  useEffect(() => {
    if (workflow.stage === previousStage.current) return;
    const target =
      workflow.stage === "configure"
        ? configureRef.current
        : workflow.stage === "enqueuing" || workflow.stage === "enqueued"
          ? processingRef.current
          : null;
    previousStage.current = workflow.stage;
    requestAnimationFrame(() =>
      target?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  }, [workflow.stage]);

  function parseEntry(entry: FileEntry) {
    const generation = entry.generation;
    prepareSrt(entry.file)
      .then((prepare) => {
        setWorkflow((previous) => {
          if (previous.stage !== "configure") return previous;
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
        setWorkflow((previous) => {
          if (previous.stage !== "configure") return previous;
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
    setWorkflow({ ...EMPTY_WORKFLOW, stage: "configure", entries });
    entries.forEach(parseEntry);
  }

  function updateEntries(change: (entries: FileEntry[]) => FileEntry[]) {
    setWorkflow((previous) =>
      previous.stage === "configure"
        ? { ...previous, entries: change(previous.entries) }
        : previous,
    );
  }

  function retry(id: string) {
    if (workflow.stage !== "configure") return;
    const current = workflow.entries.find((entry) => entry.id === id);
    if (!current) return;
    const retried: FileEntry = {
      ...current,
      status: "parsing",
      generation: current.generation + 1,
      error: undefined,
      prepare: undefined,
    };
    setWorkflow((previous) => ({
      ...previous,
      entries: previous.entries.map((entry) =>
        entry.id === id ? retried : entry,
      ),
    }));
    parseEntry(retried);
  }

  async function handleProcess(worker: string, targets: string[]) {
    if (workflow.stage !== "configure") return;
    const snapshot = workflow.entries;
    const entries = snapshot.filter(
      (entry) =>
        entry.status === "ready" &&
        entry.prepare &&
        entry.sourceLang &&
        targets.some((target) => target !== entry.sourceLang),
    );
    setWorkflow((previous) => ({
      ...previous,
      stage: "enqueuing",
      worker,
      targets,
    }));
    const jobs: EnqueuedJob[] = [];
    const enqueueFailures: EnqueueFailure[] = [];
    for (let offset = 0; offset < entries.length; offset += 4) {
      const chunk = entries.slice(offset, offset + 4);
      const results = await Promise.allSettled(
        chunk.map((entry) =>
          startJob({
            cues: entry.prepare!.cues,
            sourceLang: entry.sourceLang!,
            targets: targets.filter((target) => target !== entry.sourceLang),
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
          enqueueFailures.push({
            entry,
            message: errMessage(result.reason, "failed to queue"),
          });
      });
    }
    setWorkflow((previous) => ({
      ...previous,
      stage: "enqueued",
      jobs,
      enqueueFailures,
    }));
  }

  const handleJobTerminal = useCallback(
    (jobId: string, result: JobStatusResponse) => {
      setWorkflow((previous) =>
        previous.terminalJobs[jobId]
          ? previous
          : {
              ...previous,
              terminalJobs: { ...previous.terminalJobs, [jobId]: result },
            },
      );
    },
    [],
  );

  const restart = useCallback(() => {
    previewRevealed.current = false;
    setWorkflow(EMPTY_WORKFLOW);
    setTab("translate");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const doneJobs = workflow.jobs.filter(
    (job) => workflow.terminalJobs[job.jobId]?.status === "done",
  );
  const failedJobs = workflow.jobs.filter(
    (job) => workflow.terminalJobs[job.jobId]?.status === "failed",
  );
  const hasStepFour =
    doneJobs.length > 0 ||
    failedJobs.length > 0 ||
    workflow.enqueueFailures.length > 0;

  useEffect(() => {
    if (!hasStepFour || previewRevealed.current) return;
    previewRevealed.current = true;
    requestAnimationFrame(() =>
      previewRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      }),
    );
  }, [hasStepFour]);

  if (session === undefined) return <div className="min-h-screen bg-surface" />;
  if (session === null) return <LandingScreen />;
  if (showLanding)
    return <LandingScreen signedIn onOpenApp={() => setShowLanding(false)} />;

  return (
    <div className="min-h-screen bg-page text-ink">
      <nav className="sticky top-0 z-20 border-b border-border/70 bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-3 sm:gap-5 sm:py-4">
          <FlowLogo />
          <div className="flex min-w-0 flex-1 items-center justify-center overflow-x-auto">
            <TabButton active={false} onClick={() => setShowLanding(true)}>
              Home
            </TabButton>
            {(["translate", "jobs", "auth", "billing"] as Tab[]).map((item) => (
              <TabButton
                key={item}
                active={tab === item}
                onClick={() => setTab(item)}
              >
                {item === "jobs"
                  ? "History"
                  : item[0].toUpperCase() + item.slice(1)}
              </TabButton>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {session.is_admin && (
              <a
                href="/admin/"
                className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-subtle"
              >
                Admin
              </a>
            )}
            <button
              type="button"
              onClick={() =>
                setTheme((value) => (value === "light" ? "dark" : "light"))
              }
              className="rounded-lg border border-border bg-surface-inset p-2"
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            >
              {theme === "light" ? "☾" : "☀"}
            </button>
          </div>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-5 py-10 sm:py-12">
        {tab === "jobs" && <JobsScreen />}
        {tab === "auth" && <AuthScreen />}
        {tab === "billing" && (
          <BillingScreen
            checkoutStatus={checkoutStatus}
            onCheckoutStatusHandled={() => setCheckoutStatus(null)}
          />
        )}
        {tab === "translate" && (
          <div className="space-y-10">
            <div
              className={
                workflow.stage !== "idle"
                  ? "pointer-events-none opacity-65"
                  : ""
              }
            >
              <UploadFlow
                onSubmit={submit}
                readOnly={workflow.stage !== "idle"}
              />
            </div>
            {workflow.stage !== "idle" && (
              <section ref={configureRef} className="scroll-mt-6">
                <ConfigureScreen
                  entries={workflow.entries}
                  readOnly={workflow.stage !== "configure"}
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
              </section>
            )}
            {(workflow.stage === "enqueuing" ||
              workflow.stage === "enqueued") && (
              <section ref={processingRef} className="scroll-mt-6">
                {workflow.stage === "enqueuing" ? (
                  <Card className="p-6">
                    <SectionHeader
                      index="Step 3 / 4"
                      title="Queueing translations"
                      detail={`Preparing ${workflow.entries.filter((entry) => entry.status === "ready").length} files…`}
                    />
                    <div className="flow-progress mt-5 h-2 rounded-full" />
                  </Card>
                ) : (
                  <ProcessingScreen
                    jobs={workflow.jobs.map((job) => ({
                      jobId: job.jobId,
                      name: job.entry.name,
                    }))}
                    onJobTerminal={handleJobTerminal}
                  />
                )}
              </section>
            )}
            {workflow.stage === "enqueued" && hasStepFour && (
              <section ref={previewRef} className="scroll-mt-6 space-y-5 rise">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <SectionHeader
                    index="Step 4 / 4"
                    title="Preview & arrange"
                    detail="Reorder subtitle layers, preview the result, then download."
                  />
                  <Button variant="ghost" onClick={restart}>
                    Start over
                  </Button>
                </div>
                {workflow.enqueueFailures.map((failure) => (
                  <FailureCard
                    key={failure.entry.id}
                    name={failure.entry.name}
                    detail={failure.message}
                    label="Queue failed"
                  />
                ))}
                {failedJobs.map((job) => {
                  const result = workflow.terminalJobs[job.jobId];
                  return (
                    <FailureCard
                      key={job.jobId}
                      name={job.entry.name}
                      label={result.error_kind ?? "Translation failed"}
                      detail={
                        result.error ??
                        "The worker could not complete this job."
                      }
                    />
                  );
                })}
                {doneJobs.map((job) => (
                  <div key={job.jobId} className="space-y-2">
                    <h3 className="font-semibold">{job.entry.name}</h3>
                    <StackedOutput
                      jobId={job.jobId}
                      sourceLang={job.entry.sourceLang!}
                      targetLangs={workflow.targets.filter(
                        (target) => target !== job.entry.sourceLang,
                      )}
                    />
                  </div>
                ))}
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

function FailureCard({
  name,
  label,
  detail,
}: {
  name: string;
  label: string;
  detail: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-900"
    >
      <p className="font-semibold">{name}</p>
      <p className="mt-1 font-mono text-xs uppercase">{label}</p>
      <p className="mt-2 text-sm">{detail}</p>
    </div>
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
      aria-current={active ? "page" : undefined}
      className={`whitespace-nowrap rounded-full px-3 py-2 text-sm transition sm:px-4 ${active ? "bg-[#14181F] font-semibold text-white" : "text-ink-muted hover:bg-surface-subtle hover:text-ink"}`}
    >
      {children}
    </button>
  );
}

export function UploadFlow({
  onSubmit,
  readOnly = false,
}: {
  onSubmit: (files: File[]) => void;
  readOnly?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  function submit(selected: File[]) {
    if (readOnly) return;
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
    <section className="rise">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="text-3xl font-bold tracking-[-.03em]">
            New translation
          </h1>
          <p className="mt-2 text-[15px] text-ink-muted">
            Drop your subtitle files, choose target languages, and translate
            them all at once.
          </p>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[.14em] text-faint">
          Step 1 · Upload &amp; configure
        </p>
      </div>
      <div
        role="button"
        tabIndex={readOnly ? -1 : 0}
        aria-disabled={readOnly}
        aria-label="Drop .srt files here, or activate to pick files"
        onDragOver={(event) => {
          event.preventDefault();
          if (!readOnly) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          submit(Array.from(event.dataTransfer.files));
        }}
        onClick={() => !readOnly && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (!readOnly && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`mt-6 rounded-2xl border-2 border-dashed p-10 text-center sm:p-12 ${readOnly ? "cursor-default border-border bg-surface-subtle opacity-60" : dragging ? "cursor-pointer border-accent bg-accent-soft" : "cursor-pointer border-accent/60 bg-accent-soft/50"}`}
      >
        <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl border border-border bg-surface text-2xl font-bold text-accent shadow-[0_10px_22px_-12px_rgba(0,167,196,.5)]">
          ↥
        </div>
        <p className="text-lg font-semibold">
          {readOnly ? "Files locked for this run" : "Drop your .srt files here"}
        </p>
        <p className="mt-1 text-[13.5px] text-ink-muted">
          {readOnly
            ? "Start over to choose another batch."
            : `or browse — batch upload supported · up to ${MAX_BATCH} files, 4 MiB each`}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          disabled={readOnly}
          className="hidden"
          onChange={(event) => {
            submit(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>
      {message && <ErrorBanner>{message}</ErrorBanner>}
    </section>
  );
}
