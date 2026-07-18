import { useRef, useState } from "react";

import { ErrorBanner } from "./components.tsx";
import { SectionHeader } from "./ui.tsx";

export const MAX_BATCH = 20;

const ACCEPT = ".srt";

function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".srt"))
    return "must have a .srt extension";
  if (file.size === 0) return "is empty";
  if (file.size > 4 * 1024 * 1024) return "exceeds the 4 MiB limit";
  return null;
}

export function UploadFlow({
  onSubmit,
  onLoadSample,
  showSample = true,
  readOnly = false,
}: {
  onSubmit: (files: File[]) => void;
  onLoadSample: () => void;
  showSample?: boolean;
  readOnly?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  function submit(selected: File[]) {
    if (readOnly) return;
    const capped = selected.slice(0, MAX_BATCH);
    const accepted = capped.filter((file) => validateFile(file) === null);
    const rejected =
      capped.length -
      accepted.length +
      Math.max(0, selected.length - MAX_BATCH);
    setMessage(
      rejected > 0
        ? `${accepted.length} accepted, ${rejected} rejected${selected.length > MAX_BATCH ? ` (maximum ${MAX_BATCH} files)` : ""}.`
        : null,
    );
    if (accepted.length > 0) onSubmit(accepted);
  }
  return (
    <section className="rise">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <SectionHeader
          index="Step 1 / 3"
          title="Upload subtitles"
          detail="Drop your subtitle files, choose target languages, and translate them all at once."
        />
        {showSample && (
          <button
            type="button"
            disabled={readOnly}
            onClick={onLoadSample}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)] transition-colors hover:bg-accent-deep hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
          >
            Load sample SRT
          </button>
        )}
      </div>
      <div
        role="button"
        tabIndex={readOnly ? -1 : 0}
        aria-disabled={readOnly}
        aria-label="Drop .srt files here, or activate to pick files"
        onDragOver={(event) => {
          event.preventDefault();
          if (!readOnly) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          submit(Array.from(event.dataTransfer.files));
        }}
        onClick={() => !readOnly && inputRef.current?.click()}
        onKeyDown={(event) => {
          if (!readOnly && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            inputRef.current?.click();
          }
        }}
        className={`mt-6 rounded-2xl border-2 border-dashed p-10 text-center sm:p-12 ${readOnly ? "cursor-default border-border bg-surface-subtle opacity-60" : dragging ? "cursor-pointer border-accent bg-accent-soft" : "cursor-pointer border-accent/60 bg-accent-soft/50"}`}
      >
        <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl border border-border bg-surface text-2xl font-bold text-accent shadow-[0_10px_22px_-12px_rgba(0,167,196,.5)]">
          ↥
        </div>
        <p className="text-lg font-semibold">
          {readOnly ? "Files locked for this run" : "Drop your .srt files here"}
        </p>
        <p className="mt-1 text-[13.5px] text-ink-muted">
          {readOnly
            ? "Start over to choose another batch."
            : `or browse — batch upload supported · up to ${MAX_BATCH} files, 4 MiB each`}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          disabled={readOnly}
          className="hidden"
          onChange={(event) => {
            submit(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
      </div>
      {message && <ErrorBanner>{message}</ErrorBanner>}
    </section>
  );
}
