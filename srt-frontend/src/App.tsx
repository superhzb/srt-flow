import { useEffect, useRef, useState } from "react";

import {
  errMessage,
  prepareSrt,
  startJob,
  type JobResult,
  type PrepareResponse,
} from "./api.ts";
import { AuthScreen } from "./AuthScreen.tsx";
import { BillingScreen } from "./BillingScreen.tsx";
import { CuesView } from "./CuesView.tsx";
import { ConfigureScreen } from "./ConfigureScreen.tsx";
import { DbScreen } from "./DbScreen.tsx";
import { ErrorBanner } from "./components.tsx";
import { JobsScreen } from "./JobsScreen.tsx";
import { ProcessingScreen } from "./ProcessingScreen.tsx";
import { ResultsScreen } from "./ResultsScreen.tsx";

type State =
  | { kind: "idle" }
  | { kind: "parsing"; fileName: string }
  | { kind: "parseError"; message: string }
  | {
      kind: "configure";
      fileName: string;
      prepare: PrepareResponse;
    }
  | {
      kind: "translating";
      fileName: string;
      prepare: PrepareResponse;
      workerId: string;
      workerLabel: string;
      sourceLang: string;
      targets: string[];
      jobId: string;
    }
  | {
      kind: "translateError";
      fileName: string;
      prepare: PrepareResponse;
      message: string;
    }
  | {
      kind: "results";
      fileName: string;
      prepare: PrepareResponse;
      jobId: string;
      results: JobResult[];
    };

type Tab = "upload" | "jobs" | "db" | "auth" | "billing";
type Theme = "light" | "dark";

function initialTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
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
      // Keep the toggle functional when storage is unavailable.
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

  async function submit(file: File) {
    setState({ kind: "parsing", fileName: file.name });
    try {
      const prepare = await prepareSrt(file);
      setState({ kind: "configure", fileName: file.name, prepare });
    } catch (e) {
      setState({
        kind: "parseError",
        message: errMessage(e, "request failed"),
      });
    }
  }

  function handleProcess(
    workerId: string,
    workerLabel: string,
    sourceLang: string,
    targets: string[],
  ) {
    if (state.kind !== "configure") return;
    startJob({
      cues: state.prepare.cues,
      sourceLang,
      targets,
      worker: workerId,
    })
      .then(({ job_id }) => {
        setState({
          kind: "translating",
          fileName: state.fileName,
          prepare: state.prepare,
          workerId,
          workerLabel,
          sourceLang,
          targets,
          jobId: job_id,
        });
      })
      .catch((e: unknown) => {
        setState({
          kind: "translateError",
          fileName: state.fileName,
          prepare: state.prepare,
          message: errMessage(e, "failed to start translation"),
        });
      });
  }

  function handleDone(jobId: string, results: JobResult[]) {
    setState((prev) =>
      prev.kind === "translating"
        ? {
            kind: "results",
            fileName: prev.fileName,
            prepare: prev.prepare,
            jobId,
            results,
          }
        : prev,
    );
  }

  function handleError(message: string) {
    setState((prev) =>
      prev.kind === "translating"
        ? {
            kind: "translateError",
            fileName: prev.fileName,
            prepare: prev.prepare,
            message,
          }
        : prev,
    );
  }

  function restart() {
    setState({ kind: "idle" });
    setTab("upload");
  }

  const inUploadPhase =
    state.kind === "idle" ||
    state.kind === "parsing" ||
    state.kind === "parseError";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="max-w-7xl mx-auto px-4 py-10 sm:px-6 lg:px-8">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">srt-flow</h1>
            <p className="text-sm text-slate-600 mt-1">
              Slice 3 — translate an <code>.srt</code> file. Jobs persist across
              restarts.
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              setTheme((current) => (current === "light" ? "dark" : "light"))
            }
            className="rounded-md border border-slate-300 bg-white p-2 text-slate-600 hover:bg-slate-50 hover:text-slate-900"
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          >
            {theme === "light" ? (
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z"
                />
              </svg>
            ) : (
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="4" />
                <path
                  strokeLinecap="round"
                  d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"
                />
              </svg>
            )}
          </button>
        </header>

        <nav className="mb-6 flex gap-1 border-b border-slate-200">
          <TabButton active={tab === "upload"} onClick={() => setTab("upload")}>
            Upload
          </TabButton>
          <TabButton active={tab === "jobs"} onClick={() => setTab("jobs")}>
            Jobs
          </TabButton>
          <TabButton active={tab === "db"} onClick={() => setTab("db")}>
            DB
          </TabButton>
          <TabButton active={tab === "auth"} onClick={() => setTab("auth")}>
            Auth
          </TabButton>
          <TabButton
            active={tab === "billing"}
            onClick={() => setTab("billing")}
          >
            Billing
          </TabButton>
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

        {tab === "upload" && inUploadPhase && (
          <UploadFlow
            parsing={state.kind === "parsing"}
            parsingName={state.kind === "parsing" ? state.fileName : undefined}
            parseError={state.kind === "parseError" ? state.message : null}
            onSubmit={submit}
          />
        )}

        {tab === "upload" && state.kind === "configure" && (
          <ConfigureScreen
            fileName={state.fileName}
            prepare={state.prepare}
            onProcess={handleProcess}
            onBack={restart}
          />
        )}

        {tab === "upload" && state.kind === "translating" && (
          <ProcessingScreen
            fileName={state.fileName}
            workerLabel={state.workerLabel}
            sourceLang={state.sourceLang}
            targets={state.targets}
            jobId={state.jobId}
            onDone={(results) => handleDone(state.jobId, results)}
            onError={handleError}
          />
        )}

        {tab === "upload" && state.kind === "translateError" && (
          <div className="mt-6 space-y-3">
            <ErrorBanner>
              <span className="font-semibold">Translation failed: </span>
              {state.message}
            </ErrorBanner>
            <button
              type="button"
              onClick={() =>
                setState({
                  kind: "configure",
                  fileName: state.fileName,
                  prepare: state.prepare,
                })
              }
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
            >
              Back to configure
            </button>
          </div>
        )}

        {tab === "upload" && state.kind === "results" && (
          <ResultsScreen
            jobId={state.jobId}
            results={state.results}
            onRestart={restart}
            onViewJobs={() => setTab("jobs")}
          />
        )}

        {tab === "upload" && state.kind === "configure" && (
          <details className="mt-8">
            <summary className="cursor-pointer text-sm text-slate-600">
              preview parsed cues
            </summary>
            <CuesView
              result={{ cues: state.prepare.cues, count: state.prepare.count }}
            />
          </details>
        )}
      </div>
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
      className={`border-b-2 px-4 py-2 text-sm font-medium ${
        active
          ? "border-indigo-600 text-indigo-700"
          : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
      }`}
    >
      {children}
    </button>
  );
}

const ACCEPT = ".srt";

function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".srt"))
    return "file must have a .srt extension";
  if (file.size === 0) return "file is empty";
  if (file.size > 4 * 1024 * 1024) return "file exceeds 4 MiB limit";
  return null;
}

/**
 * Upload drop zone + parsing/parse-error feedback. Owns the file input and
 * drag state; App owns the state machine and tab routing (#22).
 */
function UploadFlow({
  parsing,
  parsingName,
  parseError,
  onSubmit,
}: {
  parsing: boolean;
  parsingName?: string;
  parseError: string | null;
  onSubmit: (file: File) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function submit(file: File) {
    const err = validateFile(file);
    if (err) {
      setValidationError(err);
      return;
    }
    setValidationError(null);
    onSubmit(file);
  }

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop an .srt file here, or activate to pick one"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void submit(file);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
          dragging
            ? "border-indigo-500 bg-indigo-50"
            : "border-slate-300 bg-white"
        }`}
      >
        <p className="font-medium">Drop an .srt file here</p>
        <p className="text-sm text-slate-500 mt-1">or click to pick one</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void submit(file);
            e.target.value = "";
          }}
        />
      </div>

      {parsing && parsingName && (
        <p className="mt-6 text-sm text-slate-600">Parsing {parsingName}…</p>
      )}

      {validationError && (
        <ErrorBanner>
          <span className="font-semibold">Error: </span>
          {validationError}
        </ErrorBanner>
      )}

      {parseError && (
        <ErrorBanner>
          <span className="font-semibold">Error: </span>
          {parseError}
        </ErrorBanner>
      )}
    </>
  );
}
