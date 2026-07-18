import { useCallback, useState } from "react";

import {
  errMessage,
  googleLoginUrl,
  prepareSrt,
  retryJob,
  startJob,
  type JobStatusResponse,
} from "./api.ts";
import { savePendingTranslation } from "./clientStorage.ts";
import { effectiveTargets, type FileEntry } from "./fileEntry.ts";

export type EnqueuedJob = { entry: FileEntry; jobId: string };
export type EnqueueFailure = { entry: FileEntry; message: string };
export type Stage = "idle" | "configure" | "demo" | "enqueuing" | "enqueued";
export type Workflow = {
  stage: Stage;
  entries: FileEntry[];
  worker: string;
  targets: string[];
  jobs: EnqueuedJob[];
  enqueueFailures: EnqueueFailure[];
  terminalJobs: Record<string, JobStatusResponse>;
  // Bumped per job on retry to remount its poller and resume polling.
  retryNonce: Record<string, number>;
};

export const EMPTY_WORKFLOW: Workflow = {
  stage: "idle",
  entries: [],
  // Selected once ConfigureScreen loads /api/workers; the backend rejects an
  // unregistered worker id, so we never default to a hardcoded literal.
  worker: "",
  targets: [],
  jobs: [],
  enqueueFailures: [],
  terminalJobs: {},
  retryNonce: {},
};

/**
 * Owns the translate-workflow state machine and the operations that only
 * touch that state (parse, submit, retry, enqueue, job-terminal tracking).
 * Tab/modal/session orchestration stays in App and drives this via the
 * returned `setWorkflow`/`reset`.
 */
export function useWorkflow() {
  const [workflow, setWorkflow] = useState<Workflow>(EMPTY_WORKFLOW);

  const reset = useCallback(() => setWorkflow(EMPTY_WORKFLOW), []);

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
                      ? prepare.bilingual.line_langs[0]
                      : (prepare.detected_lang ?? ""),
                    sourceLine: prepare.bilingual ? 0 : undefined,
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

  async function startRealProcessing() {
    if (workflow.stage !== "configure") return;
    const { worker, targets } = workflow;
    const snapshot = workflow.entries;
    const entries = snapshot.filter(
      (entry) =>
        entry.status === "ready" &&
        entry.prepare &&
        entry.sourceLang &&
        effectiveTargets(entry, targets).length > 0,
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
            targets: effectiveTargets(entry, targets),
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

  const handleRetryJob = useCallback(async (jobId: string) => {
    // Server resets the row to pending and re-queues it (input.srt retained).
    await retryJob(jobId);
    // Drop the terminal snapshot and bump the nonce so the poller remounts
    // and transitions failed → processing without a re-upload.
    setWorkflow((previous) => {
      const nextTerminal = { ...previous.terminalJobs };
      delete nextTerminal[jobId];
      return {
        ...previous,
        terminalJobs: nextTerminal,
        retryNonce: {
          ...previous.retryNonce,
          [jobId]: (previous.retryNonce[jobId] ?? 0) + 1,
        },
      };
    });
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

  return {
    workflow,
    setWorkflow,
    reset,
    submit,
    updateEntries,
    retry,
    startRealProcessing,
    signInWithPendingWork,
    handleJobTerminal,
    handleRetryJob,
    doneJobs,
    failedJobs,
    processingComplete,
  };
}
