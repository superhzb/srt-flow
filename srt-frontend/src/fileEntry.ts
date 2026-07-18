import type { PrepareResponse } from "./api.ts";

export interface FileEntry {
  id: string;
  file: File;
  name: string;
  status: "parsing" | "ready" | "error";
  generation: number;
  prepare?: PrepareResponse;
  sourceLang?: string;
  sourceLine?: number;
  error?: string;
}

export function carriedLanguage(entry: FileEntry): string | undefined {
  const langs = entry.prepare?.bilingual?.line_langs;
  return langs && entry.sourceLine !== undefined
    ? langs[1 - entry.sourceLine]
    : undefined;
}

export function effectiveTargets(
  entry: FileEntry,
  targets: Iterable<string>,
): string[] {
  const carried = carriedLanguage(entry);
  return [...targets].filter(
    (target) => target !== entry.sourceLang && target !== carried,
  );
}
