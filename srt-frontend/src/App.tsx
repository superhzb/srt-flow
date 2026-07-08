import { useRef, useState } from "react";

import {
  prepareSrt,
  startTranslate,
  type JobResult,
  type PrepareResponse,
} from "./api.ts";
import { CuesView } from "./CuesView.tsx";
import { ConfigureScreen } from "./ConfigureScreen.tsx";
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
      results: JobResult[];
    };

const ACCEPT = ".srt";

function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".srt")) return "file must have a .srt extension";
  if (file.size === 0) return "file is empty";
  if (file.size > 4 * 1024 * 1024) return "file exceeds 4 MiB limit";
  return null;
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit(file: File) {
    const err = validateFile(file);
    if (err) {
      setState({ kind: "parseError", message: err });
      return;
    }
    setState({ kind: "parsing", fileName: file.name });
    try {
      const prepare = await prepareSrt(file);
      setState({ kind: "configure", fileName: file.name, prepare });
    } catch (e) {
      setState({
        kind: "parseError",
        message: e instanceof Error ? e.message : "request failed",
      });
    }
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void submit(file);
  }

  function handleProcess(
    workerId: string,
    sourceLang: string,
    targets: string[],
  ) {
    if (state.kind !== "configure") return;
    startTranslate({
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
          workerLabel: workerId,
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
          message: e instanceof Error ? e.message : "failed to start translation",
        });
      });
  }

  function handleDone(results: JobResult[]) {
    setState((prev) =>
      prev.kind === "translating"
        ? {
            kind: "results",
            fileName: prev.fileName,
            prepare: prev.prepare,
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
  }

  // Hide the drop zone once we leave the idle/parsing/parseError upload phase.
  const showUpload =
    state.kind === "idle" ||
    state.kind === "parsing" ||
    state.kind === "parseError";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="max-w-4xl mx-auto px-4 py-10">
        <header className="mb-6">
          <h1 className="text-2xl font-bold">srt-flow</h1>
          <p className="text-sm text-slate-600 mt-1">
            Slice 2 — translate an <code>.srt</code> file into one or more languages.
          </p>
        </header>

        {showUpload && (
          <>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition ${
                dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-white"
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

            {state.kind === "parsing" && (
              <p className="mt-6 text-sm text-slate-600">
                Parsing {state.fileName}…
              </p>
            )}

            {state.kind === "parseError" && (
              <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <span className="font-semibold">Error: </span>
                {state.message}
              </div>
            )}
          </>
        )}

        {state.kind === "configure" && (
          <ConfigureScreen
            fileName={state.fileName}
            prepare={state.prepare}
            onProcess={handleProcess}
            onBack={restart}
          />
        )}

        {state.kind === "translating" && (
          <ProcessingScreen
            fileName={state.fileName}
            workerLabel={state.workerLabel}
            sourceLang={state.sourceLang}
            targets={state.targets}
            jobId={state.jobId}
            onDone={handleDone}
            onError={handleError}
          />
        )}

        {state.kind === "translateError" && (
          <div className="mt-6 space-y-3">
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              <span className="font-semibold">Translation failed: </span>
              {state.message}
            </div>
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

        {state.kind === "results" && (
          <ResultsScreen
            fileName={state.fileName}
            prepare={state.prepare}
            results={state.results}
            onRestart={restart}
          />
        )}

        {state.kind === "configure" && (
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
