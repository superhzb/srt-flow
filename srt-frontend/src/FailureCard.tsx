import { useState } from "react";

import { errMessage, type JobErrorKind } from "./api.ts";
import { errorCopy } from "./errorCopy.ts";
import { SUPPORT_EMAIL } from "./legal.ts";
import { Button } from "./ui.tsx";

export function FailureCard({
  name,
  title,
  description,
  errorKind,
  error,
  errorDetail,
  failedTarget,
  showNotCharged = false,
  onRetry,
}: {
  name: string;
  // Provide title/description directly (e.g. queue failures), or an
  // errorKind to look up friendly copy for a job failure.
  title?: string;
  description?: string;
  errorKind?: JobErrorKind | null;
  error?: string;
  errorDetail?: string;
  failedTarget?: string;
  showNotCharged?: boolean;
  onRetry?: () => void | Promise<void>;
}) {
  const copy = errorCopy(errorKind);
  const shownTitle = title ?? copy.title;
  const shownDescription = description ?? copy.description;
  const canRetry = onRetry != null && copy.retryable;
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const hasTechnical = Boolean(errorKind || error || errorDetail);

  async function handleRetry() {
    if (!onRetry) return;
    setRetrying(true);
    setRetryError(null);
    try {
      await onRetry();
    } catch (e) {
      setRetrying(false);
      setRetryError(errMessage(e, "retry failed"));
    }
    // On success the card unmounts (job leaves the failed set) — no reset.
  }

  return (
    <div
      role="alert"
      className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-900"
    >
      <p className="text-xs font-medium text-red-700">{name}</p>
      <p className="mt-1 font-semibold">{shownTitle}</p>
      <p className="mt-1 text-sm">{shownDescription}</p>
      {showNotCharged && (
        <p className="mt-2 text-sm font-medium">
          You weren't charged for this job.
        </p>
      )}
      {canRetry && (
        <div className="mt-3">
          <Button onClick={() => void handleRetry()} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry translation"}
          </Button>
        </div>
      )}
      {retryError && <p className="mt-2 text-sm">{retryError}</p>}
      <p className="mt-3 text-sm text-red-800">
        Still stuck? Email{" "}
        <a
          href={`mailto:${SUPPORT_EMAIL}`}
          className="font-medium underline underline-offset-2"
        >
          {SUPPORT_EMAIL}
        </a>
        .
      </p>
      {hasTechnical && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-red-700">
            Technical details
          </summary>
          <dl className="mt-2 space-y-1 font-mono break-words">
            {errorKind && (
              <div>
                <dt className="inline text-red-700">kind: </dt>
                <dd className="inline">{errorKind}</dd>
              </div>
            )}
            {failedTarget && (
              <div>
                <dt className="inline text-red-700">target: </dt>
                <dd className="inline">{failedTarget}</dd>
              </div>
            )}
            {(errorDetail ?? error) && (
              <div>
                <dt className="inline text-red-700">detail: </dt>
                <dd className="inline">{errorDetail ?? error}</dd>
              </div>
            )}
          </dl>
        </details>
      )}
    </div>
  );
}
