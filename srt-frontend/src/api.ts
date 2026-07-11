// Typed client for the srt-flow backend.
//
// Slice 3: jobs are durable. The poll response shape changed:
//   slice 2: results?: [{ lang, srt }]            // inline text
//   slice 3: results?: [{ lang, download_url }]   // hit /api/jobs/{id}/download
// The endpoint prefix also renamed: /api/translate* → /api/jobs*.

import { apiFetch } from "./lib.ts";

export { errMessage } from "./lib.ts";

export interface Cue {
  index: number;
  start: string;
  end: string;
  text: string;
}

export interface ParseResponse {
  cues: Cue[];
  count: number;
}

export interface PrepareResponse {
  cues: Cue[];
  count: number;
  detected_lang: string | null;
  confidence: number;
}

export interface WorkerInfo {
  id: string;
  label: string;
  healthy: boolean;
}

export interface LanguageInfo {
  code: string;
  name: string;
}

export type JobStatus = "pending" | "processing" | "done" | "failed";
export type JobErrorKind = "worker_stream" | "internal" | "landing" | string;

// Slice-3 result shape: no inline srt — fetch via download_url.
export interface JobResult {
  lang: string;
  download_url: string;
}

export interface JobStatusResponse {
  id: string;
  filename: string | null;
  status: JobStatus;
  progress: number;
  worker: string;
  src_lang: string;
  tgt_langs: string[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_kind: JobErrorKind | null;
  attempts: number;
  dropped_by_target?: Record<string, number>;
  results?: JobResult[];
  error?: string;
}

export interface JobSummary {
  id: string;
  filename: string | null;
  status: JobStatus;
  worker: string;
  src_lang: string;
  tgt_langs: string[];
  progress: number;
  created_at: string;
  started_at: string | null;
  error_kind: JobErrorKind | null;
  attempts: number;
}

export interface TableInfo {
  name: string;
  count: number;
}

export interface TablePage {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  size: number;
}

export interface Me {
  email: string;
  tier: "free" | "paid";
}

export interface CheckoutResponse {
  url: string;
}

export async function prepareSrt(file: File): Promise<PrepareResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<PrepareResponse>("/api/srt/prepare", {
    method: "POST",
    body: form,
  });
}

export async function getWorkers(): Promise<WorkerInfo[]> {
  const body = await apiFetch<{ workers: WorkerInfo[] }>("/api/workers");
  return body.workers;
}

export async function getLanguages(worker: string): Promise<LanguageInfo[]> {
  const body = await apiFetch<{ languages: LanguageInfo[] }>(
    `/api/languages?worker=${encodeURIComponent(worker)}`,
  );
  return body.languages;
}

export async function startJob(params: {
  cues: Cue[];
  sourceLang: string;
  targets: string[];
  worker: string;
  filename?: string;
}): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>("/api/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      cues: params.cues,
      source_lang: params.sourceLang,
      targets: params.targets,
      worker: params.worker,
      filename: params.filename,
    }),
  });
}

export async function pollJob(jobId: string): Promise<JobStatusResponse> {
  return apiFetch<JobStatusResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function listJobs(): Promise<JobSummary[]> {
  const body = await apiFetch<{ jobs: JobSummary[] }>("/api/jobs");
  return body.jobs;
}

export async function listTables(): Promise<TableInfo[]> {
  return apiFetch<TableInfo[]>("/api/db/tables");
}

export async function getTableRows(
  name: string,
  page: number,
  size = 20,
): Promise<TablePage> {
  const params = new URLSearchParams({
    page: String(page),
    size: String(size),
  });
  return apiFetch<TablePage>(
    `/api/db/tables/${encodeURIComponent(name)}?${params}`,
  );
}

export async function clearAllData(): Promise<{ cleared: number }> {
  return apiFetch<{ cleared: number }>("/api/db/clear", { method: "POST" });
}

export async function getMe(): Promise<Me | null> {
  const resp = await fetch("/api/auth/me");
  if (resp.status === 401) return null;
  if (!resp.ok) throw new Error(`request failed (${resp.status})`);
  return (await resp.json()) as Me;
}

export async function logout(): Promise<void> {
  const resp = await fetch("/api/auth/logout", { method: "POST" });
  if (!resp.ok) throw new Error(`request failed (${resp.status})`);
}

export async function startCheckout(): Promise<CheckoutResponse> {
  const resp = await fetch("/api/billing/checkout", { method: "POST" });
  if (resp.status === 401) throw new Error("Log in before upgrading");
  if (resp.status === 402) throw new Error("Upgrade is required");
  if (!resp.ok) throw new Error(`request failed (${resp.status})`);
  return (await resp.json()) as CheckoutResponse;
}

export function googleLoginUrl(): string {
  return "/api/auth/google/login";
}

export async function paidCheck(): Promise<number> {
  const resp = await fetch("/api/auth/paid-check");
  if (resp.status === 200 || resp.status === 401 || resp.status === 402) {
    return resp.status;
  }
  if (!resp.ok) throw new Error(`request failed (${resp.status})`);
  return resp.status;
}

// Fetch the actual .srt bytes for a target. Used when the user wants to
// preview or download — the poll response no longer carries the text inline.
export async function fetchJobOutput(downloadUrl: string): Promise<string> {
  const resp = await fetch(downloadUrl);
  if (!resp.ok) throw new Error(`request failed (${resp.status})`);
  return await resp.text();
}
