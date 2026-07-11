import { useEffect, useMemo, useState } from "react";
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
import { errMessage, fetchStackedOutput, stackedDownloadUrl } from "./api.ts";
import { Button, MonoLabel } from "./ui.tsx";

const labels: Record<string, string> = {
  en: "EN",
  fr: "FR",
  zh: "中文",
  ja: "日本語",
  ko: "한국어",
  es: "ES",
  de: "DE",
  it: "IT",
  pt: "PT",
};
export function StackedOutput({
  jobId,
  sourceLang,
  targetLangs,
}: {
  jobId: string;
  sourceLang: string;
  targetLangs: string[];
}) {
  const key = [sourceLang, ...targetLangs].join("\0");
  const all = useMemo(() => [sourceLang, ...targetLangs], [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const [order, setOrder] = useState(all),
    [included, setIncluded] = useState(() => new Set(all));
  const [preview, setPreview] = useState<string | null>(null),
    [error, setError] = useState<string | null>(null),
    [active, setActive] = useState<string | null>(null),
    [announcement, setAnnouncement] = useState("");
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );
  const request = order.filter((x) => included.has(x));
  const orderKey = request.join(",");
  useEffect(() => {
    setOrder(all);
    setIncluded(new Set(all));
  }, [all]);
  useEffect(() => {
    if (!request.length) {
      setPreview(null);
      return;
    }
    let live = true;
    setPreview(null);
    setError(null);
    fetchStackedOutput(jobId, request)
      .then((x) => live && setPreview(x))
      .catch(
        (e) =>
          live && setError(errMessage(e, "failed to load stacked preview")),
      );
    return () => {
      live = false;
    };
  }, [jobId, orderKey]); // eslint-disable-line react-hooks/exhaustive-deps
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
  return (
    <section className="rounded-2xl border border-border bg-surface-subtle p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">Stacked output</h4>
          <p className="text-xs text-ink-muted">
            Drag languages into reading order · instant, no re-translate.
          </p>
        </div>
        <MonoLabel>{request.length} layers</MonoLabel>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={(e: DragStartEvent) => setActive(String(e.active.id))}
        onDragEnd={drop}
        onDragCancel={() => setActive(null)}
      >
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <ol className="my-4 space-y-2">
            {order.map((lang, i) => (
              <SortableRow
                key={lang}
                lang={lang}
                index={i}
                source={lang === sourceLang}
                included={included.has(lang)}
                toggle={() =>
                  setIncluded((cur) => {
                    const n = new Set(cur);
                    if (n.has(lang)) n.delete(lang);
                    else n.add(lang);
                    return n;
                  })
                }
              />
            ))}
          </ol>
        </SortableContext>
        <DragOverlay>
          {active ? (
            <div className="rounded-xl border border-accent bg-surface px-4 py-3 shadow-xl">
              ⠿ &nbsp; {labels[active] ?? active.toUpperCase()}
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <div className="flex items-center gap-4">
        {request.length ? (
          <a href={stackedDownloadUrl(jobId, request)} download>
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
      {preview && (
        <pre className="font-cjk mt-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-[#090a0d] p-5 font-mono text-xs leading-6 text-white">
          {preview}
        </pre>
      )}
    </section>
  );
}
function SortableRow({
  lang,
  index,
  source,
  included,
  toggle,
}: {
  lang: string;
  index: number;
  source: boolean;
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
      <span className="w-16 font-mono text-sm font-medium">
        {labels[lang] ?? lang.toUpperCase()}
      </span>
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
