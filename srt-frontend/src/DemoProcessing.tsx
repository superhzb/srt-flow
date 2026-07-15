import { useEffect, useState } from "react";
import { langMeta } from "./languages.ts";
import { Card, SectionHeader } from "./ui.tsx";

const STAGES = ["Parsing sample", "Translating fixtures", "Completing demo"];

export function DemoProcessing({
  sourceLang = "en",
  targetLangs = [],
  onComplete,
}: {
  sourceLang?: string;
  targetLangs?: string[];
  onComplete: () => void;
}) {
  const [stage, setStage] = useState(0);
  const complete = stage === STAGES.length;
  useEffect(() => {
    if (complete) return;
    const timer = window.setTimeout(() => setStage((value) => value + 1), 550);
    return () => window.clearTimeout(timer);
  }, [complete, stage]);
  return (
    <Card className="p-6" aria-live="polite">
      <div className="mb-3 inline-flex rounded-full bg-accent-soft px-3 py-1 font-mono text-xs font-semibold text-accent-deep">
        Demo translation · no quota used
      </div>
      <SectionHeader
        index="Step 3 / 3"
        title={complete ? "Demo translation complete" : STAGES[stage]}
        detail="This client-side preview never creates a job or contacts a worker."
      />
      <div className="mt-5 h-2 overflow-hidden rounded-full bg-surface-inset">
        <div
          className="h-full bg-accent transition-all duration-500"
          style={{ width: `${(stage / STAGES.length) * 100}%` }}
        />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
        <span
          className={`${complete ? "" : "language-flow"} inline-flex items-center gap-1 rounded-full bg-surface-subtle px-2.5 py-1`}
        >
          <span aria-hidden="true">{langMeta(sourceLang).flag}</span>
          <span>{langMeta(sourceLang).en}</span>
        </span>
        <span aria-hidden="true">→</span>
        {targetLangs.map((target, index) => (
          <span
            key={target}
            className={`${complete ? "" : "language-flow"} inline-flex items-center gap-1 rounded-full bg-surface-subtle px-2.5 py-1`}
            style={{ animationDelay: `${index * 180}ms` }}
          >
            <span aria-hidden="true">{langMeta(target).flag}</span>
            <span>{langMeta(target).en}</span>
          </span>
        ))}
      </div>
      {complete && (
        <div className="mt-5 flex justify-center rise">
          <button
            type="button"
            onClick={onComplete}
            className="inline-flex items-center gap-2 rounded-xl bg-accent px-7 py-3.5 text-sm font-bold text-[#04252c] shadow-[0_10px_24px_-12px_rgba(0,167,196,.7)]"
          >
            View result in History →
          </button>
        </div>
      )}
    </Card>
  );
}
