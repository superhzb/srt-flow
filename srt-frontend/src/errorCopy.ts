// Friendly, user-facing copy for a job's `error_kind`.
//
// Backend is the source of truth for the kind values — keep this map in sync
// with `JobErrorKind` in api.ts and the docstring in the backend's models.py.
// Unknown / null kinds fall back to a generic retryable message.

import type { JobErrorKind } from "./api.ts";

export interface ErrorCopy {
  title: string;
  description: string;
  retryable: boolean;
}

const COPY: Record<string, ErrorCopy> = {
  backend_unavailable: {
    title: "Translation service was temporarily unavailable",
    description:
      "The translation service didn't respond in time. This is usually temporary — please retry.",
    retryable: true,
  },
  worker_stream: {
    title: "Translation couldn't be completed",
    description:
      "Something went wrong while translating this file. Retrying often clears it up.",
    retryable: true,
  },
  internal: {
    title: "Something went wrong on our end",
    description:
      "An unexpected error interrupted this job. Please retry — if it keeps failing, contact support.",
    retryable: true,
  },
  landing: {
    title: "We couldn't save the results",
    description:
      "Translation finished but saving the output failed. Please retry.",
    retryable: true,
  },
  unsupported_language: {
    title: "One of the languages isn't supported",
    description:
      "A source or target language for this file isn't supported yet. Start a new translation with different languages.",
    retryable: false,
  },
  worker_config: {
    title: "This translator is unavailable",
    description:
      "The selected translation engine isn't available right now. Start a new translation and pick another.",
    retryable: false,
  },
};

const FALLBACK: ErrorCopy = {
  title: "Translation couldn't be completed",
  description:
    "Something went wrong while translating this file. Please retry, or start a new translation.",
  retryable: true,
};

export function errorCopy(kind: JobErrorKind | null | undefined): ErrorCopy {
  if (!kind) return FALLBACK;
  return COPY[kind] ?? FALLBACK;
}
