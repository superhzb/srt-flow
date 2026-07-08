// Typed client for the srt-flow backend.

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

export interface JobResult {
  lang: string;
  srt: string;
}

export interface JobStatusResponse {
  status: JobStatus;
  progress: number;
  results?: JobResult[];
  error?: string;
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

export async function startTranslate(params: {
  cues: Cue[];
  sourceLang: string;
  targets: string[];
  worker: string;
}): Promise<{ job_id: string }> {
  const resp = await fetch("/api/translate", {
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

export async function pollTranslate(jobId: string): Promise<JobStatusResponse> {
  const resp = await fetch(`/api/translate/${encodeURIComponent(jobId)}`);
  if (!resp.ok) throw await readError(resp, `request failed (${resp.status})`);
  return (await resp.json()) as JobStatusResponse;
}
