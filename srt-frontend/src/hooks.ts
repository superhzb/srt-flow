import { useEffect, useRef, useState } from "react";

import { errMessage, fetchJobOutput } from "./api.ts";

export const POLL_INTERVAL_MS = 1500;

/**
 * Lazily fetch .srt output bytes for a download_url, on demand. Dedupes the
 * fetch-on-toggle logic that lived in both ResultsScreen and JobsScreen (#21):
 * each screen renders its own layout, this hook owns the fetch/cache/error.
 */
export function useJobOutput(url: string, enabled: boolean) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || text !== null || error) return;
    let cancelled = false;
    fetchJobOutput(url)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(errMessage(e, "failed to load output"));
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, text, error, url]);

  return { text, error };
}

/**
 * Smooth a coarse, jumpy progress signal into a monotonic display value.
 *
 * The worker reports progress per *batch* and we poll only every ~1.5s, so a
 * short job's real progress goes 0 → 100 with nothing in between (#—). This
 * eases a time-based estimate toward a 90% asymptote while `active`, always
 * takes the max of (previous display, estimate, real) so it never rewinds, and
 * lets the real backend value win whenever it is higher. On the terminal tick
 * (`active` false) it snaps to `realPct` (100 when done).
 *
 * `etaSeconds` (when the backend supplies one) sets the easing time constant so
 * the estimate paces roughly with the true remaining time.
 */
export function useSmoothProgress(
  realPct: number,
  active: boolean,
  etaSeconds: number | null,
): number {
  const [display, setDisplay] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) {
      startRef.current = null;
      setDisplay((d) => Math.max(d, realPct));
      return;
    }
    if (startRef.current === null) startRef.current = Date.now();
    const tau = etaSeconds && etaSeconds > 0 ? etaSeconds * 1000 : 20000;
    const timer = window.setInterval(() => {
      const elapsed = Date.now() - (startRef.current ?? Date.now());
      const estimate = 90 * (1 - Math.exp(-elapsed / tau));
      setDisplay((d) => Math.min(99, Math.max(d, estimate, realPct)));
    }, 200);
    return () => window.clearInterval(timer);
  }, [active, realPct, etaSeconds]);

  return Math.round(display);
}

interface PollState<T> {
  result: T | null;
  error: string | null;
  /** True once `isTerminal` returned true (or a hard timeout elapsed). */
  terminal: boolean;
  /** True when the optional `maxMs` deadline elapsed before a terminal result. */
  timedOut: boolean;
}

interface PollOptions {
  /** Delay between polls (ms). Default 1500. */
  intervalMs?: number;
  /** Start paused; polling runs only while enabled. */
  enabled?: boolean;
  /** Hard deadline (ms from mount). On expiry `timedOut` flips true. */
  maxMs?: number;
  /** Fire the first fetch immediately instead of after one interval. */
  immediateFirst?: boolean;
  /** Stop + flip `terminal` on the first error (default true). Set false to
   * keep retrying until `maxMs` elapses (used by the payment-confirmation loop). */
  stopOnError?: boolean;
}

/**
 * Generic poll loop: runs `fetcher` every `intervalMs` until `isTerminal`
 * returns true (or the optional `maxMs` deadline elapses). Replaces the
 * hand-rolled `cancelled` + `setTimeout` boilerplate that was copy-pasted
 * across ProcessingScreen, JobsScreen, and BillingScreen (#20).
 *
 * `fetcher` and `isTerminal` are kept in refs so consumers don't need to
 * memoise them; the effect only restarts when the structural options change.
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  isTerminal: (result: T) => boolean,
  options: PollOptions = {},
): PollState<T> {
  const {
    intervalMs = POLL_INTERVAL_MS,
    enabled = true,
    maxMs,
    immediateFirst = false,
    stopOnError = true,
  } = options;
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [terminal, setTerminal] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  const fetcherRef = useRef(fetcher);
  const isTerminalRef = useRef(isTerminal);
  const stopOnErrorRef = useRef(stopOnError);
  fetcherRef.current = fetcher;
  isTerminalRef.current = isTerminal;
  stopOnErrorRef.current = stopOnError;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let done = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const deadline = maxMs ? Date.now() + maxMs : null;

    async function tick() {
      try {
        const r = await fetcherRef.current();
        if (cancelled || done) return;
        setResult(r);
        setError(null);
        if (isTerminalRef.current(r)) {
          done = true;
          setTerminal(true);
          return;
        }
        if (deadline !== null && Date.now() >= deadline) {
          done = true;
          setTimedOut(true);
          return;
        }
        timer = setTimeout(tick, intervalMs);
      } catch (e: unknown) {
        if (cancelled || done) return;
        const message = errMessage(e, "polling failed");
        if (stopOnErrorRef.current) {
          done = true;
          setError(message);
          setTerminal(true);
          return;
        }
        if (deadline !== null && Date.now() >= deadline) {
          done = true;
          setError(message);
          setTimedOut(true);
          return;
        }
        setError(message);
        timer = setTimeout(tick, intervalMs);
      }
    }

    timer = immediateFirst ? null : setTimeout(tick, intervalMs);
    if (immediateFirst) void tick();
    return () => {
      cancelled = true;
      done = true;
      if (timer) clearTimeout(timer);
    };
  }, [enabled, intervalMs, maxMs, immediateFirst]);

  return { result, error, terminal, timedOut };
}
