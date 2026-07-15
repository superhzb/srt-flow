import type { Cue } from "./api.ts";

function timestampMs(value: string): number {
  const match = /^(\d+):(\d{2}):(\d{2})[,.](\d{3})$/.exec(value);
  if (!match) return 0;
  const [, hours, minutes, seconds, milliseconds] = match;
  return (
    (Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds)) * 1000 +
    Number(milliseconds)
  );
}

export function sourceDurationMs(cues: Cue[]): number {
  return Math.max(0, ...cues.map((cue) => timestampMs(cue.end)));
}

export function sourceCreditMinutes(cues: Cue[]): number {
  return Math.max(1, Math.ceil(sourceDurationMs(cues) / 60_000));
}

/**
 * Billed credit minutes (option A): source minutes are charged once per
 * target language, since each language is a full translation pass. Mirrors
 * the backend `billed_minutes(source_minutes, target_count)`.
 */
export function billedCreditMinutes(
  cues: Cue[],
  languageCount: number,
): number {
  return sourceCreditMinutes(cues) * Math.max(1, languageCount);
}

export function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.ceil(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${minutes}:${String(seconds).padStart(2, "0")}`;
}
