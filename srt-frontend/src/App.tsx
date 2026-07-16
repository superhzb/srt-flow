import { useCallback, useEffect, useRef, useState } from "react";

import {
  errMessage,
  getMe,
  googleLoginUrl,
  logout,
  prepareSrt,
  startJob,
  type JobStatusResponse,
  type Me,
} from "./api.ts";
import { BillingScreen } from "./BillingScreen.tsx";
import { ConfigureScreen, type FileEntry } from "./ConfigureScreen.tsx";
import { ErrorBanner } from "./components.tsx";
import { JobsScreen } from "./JobsScreen.tsx";
import { LandingScreen } from "./LandingScreen.tsx";
import { ProcessingScreen } from "./ProcessingScreen.tsx";
import { Button, Card, FlowLogo, SectionHeader } from "./ui.tsx";
import { DecisionModal } from "./DecisionModal.tsx";
import { DemoProcessing } from "./DemoProcessing.tsx";
import { DEMO_CUES, DEMO_FILENAME, sampleFile } from "./demoFixtures.ts";
import {
  clearClientRecords,
  saveDemoEntry,
  savePendingTranslation,
  takePendingTranslation,
} from "./clientStorage.ts";

type EnqueuedJob = { entry: FileEntry; jobId: string };
type EnqueueFailure = { entry: FileEntry; message: string };
type Stage = "idle" | "configure" | "demo" | "enqueuing" | "enqueued";
type Workflow = {
  stage: Stage;
  entries: FileEntry[];
  worker: string;
  targets: string[];
  jobs: EnqueuedJob[];
  enqueueFailures: EnqueueFailure[];
  terminalJobs: Record<string, JobStatusResponse>;
};
type Tab = "translate" | "jobs" | "billing";
type Theme = "light" | "dark";

const ACCEPT = ".srt";
const EMPTY_WORKFLOW: Workflow = {
  stage: "idle",
  entries: [],
  worker: "cloud",
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
  const [showLanding, setShowLanding] = useState(
    () => window.location.pathname === "/",
  );
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [loginPromptOpen, setLoginPromptOpen] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [confirmRestored, setConfirmRestored] = useState(false);
  const [checkoutStatus, setCheckoutStatus] = useState<
    "success" | "cancel" | null
  >(null);
  const [checkoutSessionId, setCheckoutSessionId] = useState<string | null>(
    null,
  );
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const configureRef = useRef<HTMLElement>(null);
  const processingRef = useRef<HTMLElement>(null);
  const previousStage = useRef<Stage>("idle");
  const translateButtonRef = useRef<HTMLButtonElement>(null);
  const accountMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!accountMenuOpen) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAccountMenuOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [accountMenuOpen]);

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
        if (me && window.location.pathname === "/") {
          window.history.replaceState({}, "", "/app");
          setShowLanding(false);
        }
      })
      .catch(() => {
        if (live) setSession(null);
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    let live = true;
    takePendingTranslation()
      .then((pending) => {
        if (!live || !pending) return;
        setWorkflow({
          ...EMPTY_WORKFLOW,
          stage: "configure",
          entries: pending.entries,
          worker: pending.worker,
          targets: pending.targets,
        });
        setTab("translate");
        setShowLanding(false);
        setConfirmRestored(true);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [session]);

  useEffect(() => {
    const url = new URL(window.location.href);
    const checkout = url.searchParams.get("checkout");
    if (checkout !== "success" && checkout !== "cancel") return;
    const sessionId = url.searchParams.get("session_id");
    setTab("billing");
    setCheckoutStatus(checkout);
    setCheckoutSessionId(sessionId);
    url.searchParams.delete("checkout");
    url.searchParams.delete("session_id");
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
        : workflow.stage === "demo" ||
            workflow.stage === "enqueuing" ||
            workflow.stage === "enqueued"
          ? processingRef.current
          : null;
    previousStage.current = workflow.stage;
    requestAnimationFrame(() =>
      target?.scrollIntoView({ behavior: "smooth", block: "center" }),
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
                    sourceLang: prepare.bilingual
                      ? ""
                      : (prepare.detected_lang ?? ""),
                    sourceLine: undefined,
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
    setWorkflow((previous) => {
      if (previous.stage !== "configure") return previous;
      const entries = change(previous.entries);
      return entries.length === 0 ? EMPTY_WORKFLOW : { ...previous, entries };
    });
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
      sourceLang: undefined,
      sourceLine: undefined,
    };
    setWorkflow((previous) => ({
      ...previous,
      entries: previous.entries.map((entry) =>
        entry.id === id ? retried : entry,
      ),
    }));
    parseEntry(retried);
  }

  function handleProcess() {
    if (!session) {
      setDecisionError(null);
      setDecisionOpen(true);
      return;
    }
    void startRealProcessing();
  }

  async function startRealProcessing() {
    if (workflow.stage !== "configure") return;
    const { worker, targets } = workflow;
    const snapshot = workflow.entries;
    const carriedLanguage = (entry: FileEntry) => {
      const langs = entry.prepare?.bilingual?.line_langs;
      return langs && entry.sourceLine !== undefined
        ? langs[1 - entry.sourceLine]
        : undefined;
    };
    const entries = snapshot.filter(
      (entry) =>
        entry.status === "ready" &&
        entry.prepare &&
        entry.sourceLang &&
        targets.some(
          (target) =>
            target !== entry.sourceLang && target !== carriedLanguage(entry),
        ),
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
            sourceLine: entry.sourceLine,
            targets: targets.filter(
              (target) =>
                target !== entry.sourceLang &&
                target !== carriedLanguage(entry),
            ),
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

  async function signInWithPendingWork() {
    if (workflow.stage !== "configure") return;
    await savePendingTranslation({
      schemaVersion: 1,
      createdAt: Date.now(),
      entries: workflow.entries,
      worker: workflow.worker,
      targets: workflow.targets,
    });
    window.location.href = googleLoginUrl();
  }

  function startDemo() {
    const targets = workflow.targets.filter((target) => target !== "en");
    const missing = targets.find((target) => !DEMO_CUES[target]);
    if (!targets.length || missing) {
      setDecisionError(
        missing
          ? `The sample has no fixture for ${missing}. Pick a supported language.`
          : "Pick at least one target language other than English for the sample demo.",
      );
      return;
    }
    setDecisionOpen(false);
    setWorkflow((previous) => ({ ...previous, stage: "demo" }));
  }

  const completeDemo = useCallback(() => {
    const targets = workflow.targets.filter(
      (target) => target !== "en" && Boolean(DEMO_CUES[target]),
    );
    const id = crypto.randomUUID();
    void saveDemoEntry({
      schemaVersion: 1,
      id,
      createdAt: Date.now(),
      filename: DEMO_FILENAME,
      sourceLang: "en",
      targetLangs: targets,
      cuesByLanguage: Object.fromEntries(
        ["en", ...targets].map((lang) => [lang, DEMO_CUES[lang]]),
      ),
    }).then(() => {
      setWorkflow(EMPTY_WORKFLOW);
      setTab("jobs");
    });
  }, [workflow.targets]);

  async function handleLogout() {
    setAccountMenuOpen(false);
    try {
      await logout();
    } finally {
      await clearClientRecords();
    }
    setSession(null);
    setWorkflow(EMPTY_WORKFLOW);
    setTab("translate");
    setShowLanding(true);
    window.history.replaceState({}, "", "/");
  }

  function openStudio() {
    setWorkflow(EMPTY_WORKFLOW);
    setShowLanding(false);
    setTab("translate");
    window.history.replaceState({}, "", "/app");
  }

  function openTranslate() {
    setWorkflow(EMPTY_WORKFLOW);
    setShowLanding(false);
    setTab("translate");
    window.history.replaceState({}, "", "/app");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openHome() {
    setShowLanding(true);
    window.history.replaceState({}, "", "/");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function openTab(nextTab: Tab) {
    if (nextTab === "billing" && !session) {
      setLoginPromptOpen(true);
      return;
    }
    if (nextTab === "translate") {
      openTranslate();
      return;
    }
    setShowLanding(false);
    setTab(nextTab);
    window.history.replaceState({}, "", "/app");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function viewResults() {
    setWorkflow(EMPTY_WORKFLOW);
    setTab("jobs");
    window.scrollTo({ top: 0, behavior: "smooth" });
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
  const processingComplete =
    workflow.stage === "enqueued" &&
    workflow.jobs.every((job) => Boolean(workflow.terminalJobs[job.jobId]));

  if (session === undefined) return <div className="min-h-screen bg-surface" />;
  return (
    <div className="min-h-screen bg-page text-ink">
      <nav
        aria-label="Primary navigation"
        className="sticky top-0 z-20 border-b border-border/70 bg-surface/90 backdrop-blur"
      >
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-5 py-3 sm:gap-5 sm:py-4">
          <FlowLogo />
          <div className="flex min-w-0 flex-1 items-center justify-center overflow-x-auto">
            <TabButton active={showLanding} onClick={openHome}>
              Home
            </TabButton>
            {(["translate", "jobs", "billing"] as Tab[]).map((item) => (
              <TabButton
                key={item}
                active={!showLanding && tab === item}
                onClick={() => openTab(item)}
              >
                {item === "jobs"
                  ? "History"
                  : item[0].toUpperCase() + item.slice(1)}
              </TabButton>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {session?.is_admin && (
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
            {session ? (
              <div ref={accountMenuRef} className="relative">
                <button
                  type="button"
                  aria-expanded={accountMenuOpen}
                  aria-haspopup="menu"
                  onClick={() => setAccountMenuOpen((open) => !open)}
                  className="cursor-pointer rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium"
                >
                  {session.email}
                </button>
                {accountMenuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 rounded-xl border border-border bg-surface p-2 shadow-xl"
                  >
                    <p className="truncate px-2 py-1 text-xs text-ink-muted">
                      {session.email}
                    </p>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => void handleLogout()}
                      className="mt-1 w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-surface-subtle"
                    >
                      Logout
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <a
                href={googleLoginUrl()}
                className="rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium"
              >
                Sign in
              </a>
            )}
          </div>
        </div>
      </nav>
      {showLanding ? (
        <LandingScreen
          signedIn={Boolean(session)}
          onOpenApp={openStudio}
          onOpenStudio={openStudio}
        />
      ) : (
        <main className="mx-auto max-w-6xl px-5 py-10 sm:py-12">
          {tab === "jobs" && <JobsScreen guest={!session} />}
          {tab === "billing" && session && (
            <BillingScreen
              checkoutStatus={checkoutStatus}
              checkoutSessionId={checkoutSessionId}
              onCheckoutStatusHandled={() => {
                setCheckoutStatus(null);
                setCheckoutSessionId(null);
              }}
              onLogout={() => void handleLogout()}
            />
          )}
          {tab === "translate" && (
            <div className="space-y-10 pb-[40vh]">
              <div
                className={
                  workflow.stage !== "idle"
                    ? "pointer-events-none opacity-65"
                    : ""
                }
              >
                <UploadFlow
                  onSubmit={submit}
                  onLoadSample={() => submit([sampleFile()])}
                  showSample={!session}
                  readOnly={workflow.stage !== "idle"}
                />
              </div>
              {workflow.stage !== "idle" && (
                <section ref={configureRef} className="scroll-mt-24 py-4">
                  <div className="w-full">
                    <ConfigureScreen
                      entries={workflow.entries}
                      readOnly={workflow.stage !== "configure"}
                      onSourceChange={(id, sourceLang, sourceLine) =>
                        setWorkflow((previous) => {
                          if (previous.stage !== "configure") return previous;
                          const current = previous.entries.find(
                            (entry) => entry.id === id,
                          );
                          const carried =
                            sourceLine !== undefined
                              ? current?.prepare?.bilingual?.line_langs[
                                  1 - sourceLine
                                ]
                              : undefined;
                          return {
                            ...previous,
                            entries: previous.entries.map((entry) =>
                              entry.id === id
                                ? { ...entry, sourceLang, sourceLine }
                                : entry,
                            ),
                            targets: carried
                              ? previous.targets.filter(
                                  (target) => target !== carried,
                                )
                              : previous.targets,
                          };
                        })
                      }
                      onRemove={(id) =>
                        updateEntries((entries) =>
                          entries.filter((entry) => entry.id !== id),
                        )
                      }
                      onRetry={retry}
                      onProcess={handleProcess}
                      onBack={restart}
                      guest={!session}
                      targets={workflow.targets}
                      onTargetsChange={(targets) =>
                        setWorkflow((previous) => ({ ...previous, targets }))
                      }
                      translateButtonRef={translateButtonRef}
                    />
                  </div>
                </section>
              )}
              {(workflow.stage === "enqueuing" ||
                workflow.stage === "enqueued") && (
                <section ref={processingRef} className="scroll-mt-24 py-4">
                  <div className="w-full space-y-5">
                    {workflow.stage === "enqueuing" ? (
                      <Card className="p-6">
                        <SectionHeader
                          index="Step 3 / 3"
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
                        complete={processingComplete}
                        hasResults={doneJobs.length > 0}
                        onViewResults={viewResults}
                        onStartOver={restart}
                      />
                    )}
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
                  </div>
                </section>
              )}
              {workflow.stage === "demo" && (
                <section ref={processingRef} className="scroll-mt-24 py-4">
                  <div className="w-full">
                    <DemoProcessing
                      sourceLang="en"
                      targetLangs={workflow.targets.filter(
                        (target) => target !== "en",
                      )}
                      onComplete={completeDemo}
                    />
                  </div>
                </section>
              )}
            </div>
          )}
        </main>
      )}
      {decisionOpen && (
        <DecisionModal
          onSignIn={() => void signInWithPendingWork()}
          onDemo={startDemo}
          onClose={() => setDecisionOpen(false)}
          error={decisionError}
        />
      )}
      {confirmRestored && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-5">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="restore-title"
            className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-2xl"
          >
            <h2 id="restore-title" className="text-xl font-semibold">
              Your translation is ready
            </h2>
            <p className="mt-2 text-sm text-ink-muted">
              Review the restored files and languages, then confirm before using
              quota.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button
                onClick={() => {
                  setConfirmRestored(false);
                  void startRealProcessing();
                }}
              >
                Confirm and translate
              </Button>
              <Button variant="ghost" onClick={() => setConfirmRestored(false)}>
                Keep editing
              </Button>
            </div>
          </div>
        </div>
      )}
      {loginPromptOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-5"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setLoginPromptOpen(false)
          }
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="login-title"
            className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-2xl"
          >
            <h2 id="login-title" className="text-xl font-semibold">
              Sign in to open Billing
            </h2>
            <p className="mt-2 text-sm text-ink-muted">
              Billing and real translation history belong to your account.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a
                href={googleLoginUrl()}
                className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-surface"
              >
                Continue with Google
              </a>
              <Button variant="ghost" onClick={() => setLoginPromptOpen(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
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
  onLoadSample,
  showSample = true,
  readOnly = false,
}: {
  onSubmit: (files: File[]) => void;
  onLoadSample: () => void;
  showSample?: boolean;
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <SectionHeader
          index="Step 1 / 3"
          title="Upload subtitles"
          detail="Drop your subtitle files, choose target languages, and translate them all at once."
        />
        {showSample && (
          <button
            type="button"
            disabled={readOnly}
            onClick={onLoadSample}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)] transition-colors hover:bg-accent-deep hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            Load sample SRT
          </button>
        )}
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
