export type PreviewCue = {
  index: string;
  timecode: string;
  lines: string[];
};

export function parseStackedPreview(value: string): PreviewCue[] {
  return value
    .trim()
    .split(/\r?\n\s*\r?\n/)
    .map((block) => {
      const rows = block.split(/\r?\n/);
      const timecodeIndex = rows.findIndex((row) => row.includes(" --> "));
      if (timecodeIndex < 0) return null;
      return {
        index: rows.slice(0, timecodeIndex).join(" ").trim() || "—",
        timecode: rows[timecodeIndex].trim(),
        lines: rows.slice(timecodeIndex + 1).filter((row) => row.trim()),
      };
    })
    .filter((cue): cue is PreviewCue => cue !== null);
}
