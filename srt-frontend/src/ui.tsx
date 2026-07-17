import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
}) {
  const tone =
    variant === "primary"
      ? "bg-ink text-surface hover:bg-accent-deep"
      : variant === "danger"
        ? "border border-red-300 text-red-700 hover:bg-red-50"
        : "border border-border bg-surface text-ink hover:bg-surface-inset";
  return (
    <button
      {...props}
      className={`rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${tone} ${className}`}
    />
  );
}
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-border bg-surface shadow-[0_14px_40px_rgba(20,24,31,.05)] ${className}`}
    >
      {children}
    </section>
  );
}
export function MonoLabel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`font-mono text-[11px] uppercase tracking-[.12em] text-faint ${className}`}
    >
      {children}
    </span>
  );
}
export function SectionHeader({
  index,
  title,
  detail,
}: {
  index: string;
  title: string;
  detail?: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="rounded-md border border-accent bg-accent-soft px-2 py-1 font-mono text-xs text-accent-deep">
        {index}·
      </span>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {detail && <p className="mt-0.5 text-sm text-ink-muted">{detail}</p>}
      </div>
    </div>
  );
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-faint ${props.className ?? ""}`}
    />
  );
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink ${props.className ?? ""}`}
    />
  );
}
export function FlowLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5" aria-label="srt flow">
      <span
        className="flow-mark flex h-10 w-10 flex-col justify-center gap-1 rounded-[11px] bg-[#14181F] px-2 shadow-[0_7px_18px_rgba(20,24,31,.25)]"
        aria-hidden="true"
      >
        <span className="h-1 w-full rounded-full bg-accent" />
        <span className="h-1 w-[70%] rounded-full bg-info" />
        <span className="h-1 w-[88%] rounded-full bg-indigo-500" />
      </span>
      {!compact && (
        <span className="text-lg font-semibold tracking-[-.04em]">
          srt<span className="text-accent">·</span>flow
        </span>
      )}
    </div>
  );
}
