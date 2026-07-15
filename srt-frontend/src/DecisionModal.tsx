import { useEffect, useRef } from "react";

export function DecisionModal({
  onSignIn,
  onDemo,
  onClose,
  error,
}: {
  onSignIn: () => void;
  onDemo: () => void;
  onClose: () => void;
  error?: string | null;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialog.current) return;
      const focusable = [
        ...dialog.current.querySelectorAll<HTMLElement>("button"),
      ];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/55 p-5"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guest-decision-title"
        className="w-full max-w-lg rounded-2xl bg-surface p-6 shadow-2xl"
      >
        <h2 id="guest-decision-title" className="text-xl font-semibold">
          Ready to translate?
        </h2>
        <p className="mt-2 text-sm leading-6 text-ink-muted">
          Sign in for a real translation, or try a deterministic demo using our
          bundled sample. Your current setup stays here if you keep editing.
        </p>
        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800"
          >
            {error}
          </p>
        )}
        <div className="mt-6 grid gap-3">
          <button
            type="button"
            onClick={onSignIn}
            className="rounded-xl bg-ink px-4 py-3 font-semibold text-surface"
          >
            Sign in for up to 30 free minutes/month
          </button>
          <button
            type="button"
            onClick={onDemo}
            className="rounded-xl bg-accent px-4 py-3 font-semibold text-[#04252c]"
          >
            Try with sample SRT
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border px-4 py-3 font-semibold"
          >
            Keep editing
          </button>
        </div>
      </div>
    </div>
  );
}
