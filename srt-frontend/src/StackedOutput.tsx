import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  errMessage,
  fetchStackedOutput,
  stackedDownloadUrl,
  type Cue,
} from "./api.ts";
import { DEMO_DOWNLOAD_FILENAME } from "./demoFixtures.ts";
import { langMeta } from "./languages.ts";
import { parseStackedPreview } from "./stackedPreview.ts";
import { Button, MonoLabel } from "./ui.tsx";

export function StackedOutput({
  jobId,
  demoCues,
  sourceLang,
  targetLangs,
  historyHeader,
  historySidebar,
}: {
  jobId?: string;
  demoCues?: Record<string, Cue[]>;
  sourceLang: string;
  targetLangs: string[];
  historyHeader?: { filename: string; meta: string };
  historySidebar?: HTMLElement | null;
}) {
  const key = [sourceLang, ...targetLangs].join("\0");
  const all = useMemo(() => [sourceLang, ...targetLangs], [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const [order, setOrder] = useState(all),
    [included, setIncluded] = useState(() => new Set(all));
  const [preview, setPreview] = useState<string | null>(null),
    [error, setError] = useState<string | null>(null),
    [downloadUrl, setDownloadUrl] = useState<string | null>(null),
    [active, setActive] = useState<string | null>(null),
    [announcement, setAnnouncement] = useState("");
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const request = order.filter((lang) => included.has(lang));
  const orderKey = request.join(",");
  useEffect(() => {
    setOrder(all);
    setIncluded(new Set(all));
  }, [all]);
  useEffect(() => {
    if (!request.length) {
      setPreview(null);
      setDownloadUrl(null);
      return;
    }
    if (demoCues) {
      try {
        const output = stackDemoCues(demoCues, request);
        const url = URL.createObjectURL(
          new Blob([output], { type: "application/x-subrip;charset=utf-8" }),
        );
        setPreview(output);
        setError(null);
        setDownloadUrl(url);
        return () => URL.revokeObjectURL(url);
      } catch (error) {
        setPreview(null);
        setDownloadUrl(null);
        setError(errMessage(error, "unsupported demo language"));
        return;
      }
    }
    if (!jobId) return;
    let live = true;
    setPreview(null);
    setError(null);
    setDownloadUrl(stackedDownloadUrl(jobId, request));
    fetchStackedOutput(jobId, request)
      .then((x) => live && setPreview(x))
      .catch(
        (e) =>
          live && setError(errMessage(e, "failed to load stacked preview")),
      );
    return () => {
      live = false;
    };
  }, [jobId, demoCues, orderKey]); // eslint-disable-line react-hooks/exhaustive-deps
  function drop(e: DragEndEvent) {
    setActive(null);
    if (!e.over || e.active.id === e.over.id) return;
    setOrder((current) => {
      const next = arrayMove(
        current,
        current.indexOf(String(e.active.id)),
        current.indexOf(String(e.over!.id)),
      );
      const n = next.indexOf(String(e.active.id)) + 1;
      setAnnouncement(`moved ${e.active.id} to position ${n}`);
      requestAnimationFrame(() =>
        document
          .querySelector<HTMLElement>(
            `[data-sort-id="${String(e.active.id)}"] button`,
          )
          ?.focus(),
      );
      return next;
    });
  }
  const languageOrder = (
    <div
      className={
        historyHeader
          ? "overflow-hidden rounded-2xl border border-border bg-surface shadow-sm"
          : ""
      }
    >
      {historyHeader && (
        <div className="border-b border-border-subtle px-5 py-4">
          <h2 className="text-base font-semibold tracking-tight">
            Language order
          </h2>
          <p className="mt-1 font-mono text-[10.5px] text-faint">
            drag ⠿ to reorder — every line updates
          </p>
        </div>
      )}
      <div className={historyHeader ? "bg-surface-subtle p-5" : ""}>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={(e: DragStartEvent) => setActive(String(e.active.id))}
          onDragEnd={drop}
          onDragCancel={() => setActive(null)}
        >
          <SortableContext items={order} strategy={verticalListSortingStrategy}>
            <ol
              className={
                historyHeader
                  ? "flex flex-col items-start gap-2"
                  : "my-4 space-y-2"
              }
            >
              {order.map((lang, i) => (
                <SortableRow
                  key={lang}
                  lang={lang}
                  index={i}
                  source={lang === sourceLang}
                  compact={Boolean(historyHeader)}
                  included={included.has(lang)}
                  toggle={() =>
                    setIncluded((current) => {
                      const next = new Set(current);
                      if (next.has(lang)) next.delete(lang);
                      else next.add(lang);
                      return next;
                    })
                  }
                />
              ))}
            </ol>
          </SortableContext>
          {createPortal(
            <DragOverlay>
              {active ? (
                <div
                  className="flex items-center gap-2 rounded-[10px] border border-accent border-l-[3px] bg-surface px-3 py-2 shadow-[0_8px_18px_-8px_rgba(0,167,196,.45)]"
                  style={{ borderLeftColor: langMeta(active).tint }}
                >
                  <span className="font-mono text-sm text-[#c2c9d3]">⠿</span>
                  <span aria-hidden="true">{langMeta(active).flag}</span>
                  <span
                    className="font-mono text-[11px] font-bold"
                    style={{ color: langMeta(active).tint }}
                  >
                    {active.toUpperCase()}
                  </span>
                  <span className="text-xs text-ink-muted">
                    {langMeta(active).native}
                  </span>
                </div>
              ) : null}
            </DragOverlay>,
            document.body,
          )}
        </DndContext>
        <p className="sr-only" aria-live="polite">
          {announcement}
        </p>
        {!historyHeader && (
          <div className="flex items-center gap-4">
            {request.length && downloadUrl ? (
              <a
                href={downloadUrl}
                download={demoCues ? DEMO_DOWNLOAD_FILENAME : true}
              >
                <Button>Download stacked SRT</Button>
              </a>
            ) : (
              <Button disabled>Download stacked SRT</Button>
            )}
            <span className="text-xs text-ink-muted">
              {preview === null && !error && request.length
                ? "Refreshing preview…"
                : error}
            </span>
          </div>
        )}
      </div>
    </div>
  );
  return (
    <section
      className={
        historyHeader
          ? "bg-surface"
          : "rounded-2xl border border-border bg-surface-subtle p-4 sm:p-5"
      }
    >
      {historyHeader ? (
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border-subtle px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold tracking-tight">
              {historyHeader.filename}
            </h2>
            <p className="mt-1 font-mono text-[10.5px] text-faint">
              {historyHeader.meta} · {request.length} languages
            </p>
          </div>
          {request.length && downloadUrl ? (
            <a
              href={downloadUrl}
              download={demoCues ? DEMO_DOWNLOAD_FILENAME : true}
            >
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-[10px] bg-accent px-5 py-[11px] text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-14px_rgba(0,167,196,.7)] transition-colors hover:bg-accent-deep hover:text-white"
              >
                ↓ Download .srt
              </button>
            </a>
          ) : (
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 rounded-[10px] bg-accent px-5 py-[11px] text-sm font-bold text-[#04252c] opacity-45"
            >
              ↓ Download .srt
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h4 className="font-semibold">Stacked output</h4>
            <p className="text-xs text-ink-muted">
              Drag languages into reading order · instant, no re-translate.
            </p>
          </div>
          <MonoLabel>{request.length} layers</MonoLabel>
        </div>
      )}
      {historyHeader
        ? historySidebar && createPortal(languageOrder, historySidebar)
        : languageOrder}
      {preview &&
        (historyHeader ? (
          <ReviewPreview value={preview} order={request} />
        ) : (
          <pre className="font-cjk mt-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-[#090a0d] p-5 font-mono text-xs leading-6 text-white">
            {preview}
          </pre>
        ))}
      {historyHeader && preview === null && (
        <div className="bg-surface-subtle px-5 py-8 text-sm text-ink-muted">
          {error ??
            (request.length
              ? "Refreshing review…"
              : "Include at least one language to preview it.")}
        </div>
      )}
    </section>
  );
}

function stackDemoCues(
  cuesByLanguage: Record<string, Cue[]>,
  order: string[],
): string {
  const first = cuesByLanguage[order[0]];
  if (!first) throw new Error(`No demo fixture for ${order[0]}`);
  for (const lang of order) {
    if (!cuesByLanguage[lang]) throw new Error(`No demo fixture for ${lang}`);
  }
  return first
    .map((cue, index) => {
      const lines = order.map((lang) => {
        const translated = cuesByLanguage[lang][index];
        if (!translated) throw new Error(`Incomplete demo fixture for ${lang}`);
        return translated.text;
      });
      return `${cue.index}\n${cue.start} --> ${cue.end}\n${lines.join("\n")}`;
    })
    .join("\n\n")
    .concat("\n");
}

function ReviewPreview({ value, order }: { value: string; order: string[] }) {
  const cues = useMemo(() => parseStackedPreview(value), [value]);
  return (
    <div className="flow-scroll max-h-[620px] overflow-y-auto bg-surface-subtle py-1">
      {cues.map((cue, cueIndex) => (
        <article
          key={`${cue.index}-${cueIndex}`}
          className="border-b border-border-subtle px-5 py-3"
        >
          <header className="mb-2.5 flex items-baseline gap-3">
            <span className="w-7 shrink-0 font-mono text-[11px] text-faint/60">
              {cue.index}
            </span>
            <span className="font-mono text-[11.5px] text-accent-deep">
              {cue.timecode}
            </span>
          </header>
          <div className="space-y-1">
            {order.map((lang, lineIndex) => {
              const tint = langMeta(lang).tint;
              return (
                <div
                  key={lang}
                  className="flex items-start gap-2.5 border-l-2 py-0.5 pl-2.5"
                  style={{ borderLeftColor: tint }}
                >
                  <span
                    className="w-12 shrink-0 pt-0.5 font-mono text-[9.5px] font-bold uppercase tracking-[.05em]"
                    style={{ color: tint }}
                  >
                    {lang.toUpperCase()}
                  </span>
                  <span
                    className="min-w-0 whitespace-pre-wrap text-[13.5px] leading-[1.4] text-[#20242e]"
                    style={{
                      fontFamily:
                        '"JetBrains Mono", "Noto Sans SC", "Noto Sans JP", "Noto Sans KR", monospace',
                    }}
                  >
                    {cue.lines[lineIndex] ?? "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </article>
      ))}
    </div>
  );
}
function SortableRow({
  lang,
  index,
  source,
  compact,
  included,
  toggle,
}: {
  lang: string;
  index: number;
  source: boolean;
  compact: boolean;
  included: boolean;
  toggle: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: lang });
  const meta = langMeta(lang);
  if (compact) {
    return (
      <li
        ref={setNodeRef}
        data-sort-id={lang}
        style={{
          transform: CSS.Transform.toString(transform),
          transition,
          borderLeftColor: meta.tint,
        }}
        className={`flex select-none items-center gap-2 rounded-[10px] border border-l-[3px] bg-surface px-3 py-2 shadow-[0_1px_0_rgba(20,24,31,.03)] ${isDragging ? "opacity-35" : "border-border"}`}
      >
        <button
          type="button"
          {...attributes}
          {...listeners}
          aria-label={`Reorder ${lang}, position ${index + 1}`}
          className="cursor-grab touch-none font-mono text-sm text-[#c2c9d3] active:cursor-grabbing"
        >
          ⠿
        </button>
        <span aria-hidden="true">{meta.flag}</span>
        <span
          className="font-mono text-[11px] font-bold"
          style={{ color: meta.tint }}
        >
          {lang.toUpperCase()}
        </span>
        <span className="text-xs text-ink-muted">{meta.native}</span>
      </li>
    );
  }
  return (
    <li
      ref={setNodeRef}
      data-sort-id={lang}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`flex items-center gap-3 rounded-xl border border-l-4 bg-surface p-3 ${isDragging ? "border-accent opacity-40" : source ? "border-border border-l-accent" : "border-border border-l-info"}`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label={`Reorder ${lang}, position ${index + 1}`}
        className="cursor-grab touch-none rounded px-1 font-mono text-faint active:cursor-grabbing"
      >
        ⠿
      </button>
      <span aria-hidden="true">{meta.flag}</span>
      <span className="w-10 font-mono text-sm font-medium">
        {lang.toUpperCase()}
      </span>
      <span className="text-sm text-ink-muted">{meta.native}</span>
      {source && <MonoLabel>original</MonoLabel>}
      <span className="ml-auto font-mono text-[10px] text-faint">
        {index + 1}
      </span>
      <button
        type="button"
        aria-pressed={included}
        onClick={toggle}
        className={`rounded-full px-2 py-1 text-[11px] ${included ? "bg-accent-soft text-accent-deep" : "bg-surface-inset text-faint"}`}
      >
        {included ? "included" : "excluded"}
      </button>
    </li>
  );
}
