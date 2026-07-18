import { describe, expect, it } from "vitest";

import {
  carriedLanguage,
  effectiveTargets,
  type FileEntry,
} from "./fileEntry.ts";

function fileEntry(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    id: "entry-1",
    file: new File([""], "subtitles.srt"),
    name: "subtitles.srt",
    status: "ready",
    generation: 0,
    sourceLang: "en",
    ...overrides,
  };
}

describe("effectiveTargets", () => {
  it("removes the source language and preserves target order", () => {
    expect(effectiveTargets(fileEntry(), ["fr", "en", "de"])).toEqual([
      "fr",
      "de",
    ]);
  });

  it("also removes the carried language from a bilingual file", () => {
    const entry = fileEntry({
      sourceLine: 0,
      prepare: {
        cues: [],
        count: 0,
        detected_lang: null,
        confidence: 1,
        bilingual: { line_langs: ["en", "fr"] },
      },
    });

    expect(carriedLanguage(entry)).toBe("fr");
    expect(effectiveTargets(entry, new Set(["fr", "de", "en"]))).toEqual([
      "de",
    ]);
  });
});
