// Typed client for the srt-flow backend.
//
// Slice 3: jobs are durable. The poll response shape changed:
//   slice 2: results?: [{ lang, srt }]            // inline text
//   slice 3: results?: [{ lang, download_url }]   // hit /api/jobs/{id}/download
// The endpoint prefix also renamed: /api/translate* → /api/jobs*.

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

// Slice-3 result shape: no inline srt — fetch via download_url.
export interface JobResult {
  lang: string;
  download_url: string;
}

export interface JobStatusResponse {
  id: string;
  status: JobStatus;
  progress: number;
  worker: string;
  src_lang: string;
  tgt_langs: string[];
  results?: JobResult[];
  error?: string;
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  worker: string;
  src_lang: string;
  tgt_langs: string[];
  progress: number;
  created_at: string;
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

// FastAPI HTTPException detail can be a string or a list of field errors;
// normalise both into a single message.
function extractDetail(maybe: unknown, fallback: string): string {
  if (typeof maybe === "string") return maybe;
  if (Array.isArray(maybe) && maybe.length > 0) {
    const first = maybe[0];
    if (first && typeof first === "object" && "msg" in first) {
      return String((first as { msg: unknown }).msg);
    }
  }
  return fallback;
}

async function readError(resp: Response, fallback: string): Promise<Error> {
  let body: unknown = undefined;
  try {
    body = await resp.json();
  } catch {
    // fall through with generic message
  }
  const detail =
    body && typeof body === "object" && "detail" in body
      ? extractDetail((body as { detail: unknown }).detail, fallback)
      : fallback;
  return new Error(detail);
}

export async function parseSrt(file: File): Promise<ParseResponse> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/srt/parse", { method: "POST", body: form });
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as ParseResponse;
}

export async function prepareSrt(file: File): Promise<PrepareResponse> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/srt/prepare", { method: "POST", body: form });
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as PrepareResponse;
}

export async function getWorkers(): Promise<WorkerInfo[]> {
  const resp = await fetch("/api/workers");
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  const body = (await resp.json()) as { workers: WorkerInfo[] };
  return body.workers;
}

export async function getLanguages(worker: string): Promise<LanguageInfo[]> {
  const resp = await fetch(`/api/languages?worker=${encodeURIComponent(worker)}`);
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  const body = (await resp.json()) as { languages: LanguageInfo[] };
  return body.languages;
}

export async function startJob(params: {
  cues: Cue[];
  sourceLang: string;
  targets: string[];
  worker: string;
}): Promise<{ job_id: string }> {
  const resp = await fetch("/api/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      cues: params.cues,
      source_lang: params.sourceLang,
      targets: params.targets,
      worker: params.worker,
    }),
  });
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as { job_id: string };
}

export async function pollJob(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as JobStatusResponse;
}

export async function listJobs(): Promise<JobSummary[]> {
  const resp = await fetch("/api/jobs");
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  const body = (await resp.json()) as { jobs: JobSummary[] };
  return body.jobs;
}

export async function listTables(): Promise<TableInfo[]> {
  const resp = await fetch("/api/db/tables");
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as TableInfo[];
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
  const resp = await fetch(`/api/db/tables/${encodeURIComponent(name)}?${params}`);
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as TablePage;
}

export async function clearAllData(): Promise<{ cleared: number }> {
  const resp = await fetch("/api/db/clear", { method: "POST" });
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as { cleared: number };
}

export async function getMe(): Promise<Me | null> {
  const resp = await fetch("/api/auth/me");
  if (resp.status === 401) return null;
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as Me;
}

export async function logout(): Promise<void> {
  const resp = await fetch("/api/auth/logout", { method: "POST" });
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
}

export async function startCheckout(): Promise<CheckoutResponse> {
  const resp = await fetch("/api/billing/checkout", { method: "POST" });
  if (resp.status === 401) throw new Error("Log in before upgrading");
  if (resp.status === 402) throw new Error("Upgrade is required");
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
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
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return resp.status;
}

// Fetch the actual .srt bytes for a target. Used when the user wants to
// preview or download — the poll response no longer carries the text inline.
export async function fetchJobOutput(downloadUrl: string): Promise<string> {
  const resp = await fetch(downloadUrl);
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return await resp.text();
}
