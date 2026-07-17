import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePoll, useSmoothProgress } from "./hooks.ts";

/** Harness that surfaces the hook state as text for assertions. */
function Harness({
  fetcher,
  isTerminal,
  options,
}: {
  fetcher: () => Promise<unknown>;
  isTerminal: (r: unknown) => boolean;
  options?: Parameters<typeof usePoll<unknown>>[2];
}) {
  const state = usePoll(fetcher, isTerminal, options);
  return <div data-testid="state">{JSON.stringify(state)}</div>;
}

function readState() {
  return JSON.parse(screen.getByTestId("state").textContent ?? "{}") as {
    terminal: boolean;
    timedOut: boolean;
    error: string | null;
    result: unknown;
  };
}

describe("usePoll", () => {
  it("stops once the terminal predicate is satisfied", async () => {
    let calls = 0;
    const fetcher = async () => ({ n: ++calls });
    const isTerminal = (r: unknown) => (r as { n: number }).n >= 2;

    render(
      <Harness
        fetcher={fetcher}
        isTerminal={isTerminal}
        options={{ intervalMs: 5, immediateFirst: true }}
      />,
    );

    await waitFor(() => expect(readState().terminal).toBe(true));
    expect(readState().result).toEqual({ n: 2 });
    // Terminal stops further fetches.
    const callsAtTerminal = calls;
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toBe(callsAtTerminal);
  });

  it("flips terminal + error on the first error by default (stopOnError)", async () => {
    const fetcher = async () => {
      throw new Error("kaboom");
    };

    render(
      <Harness
        fetcher={fetcher}
        isTerminal={() => false}
        options={{ intervalMs: 5 }}
      />,
    );

    await waitFor(() => expect(readState().terminal).toBe(true));
    expect(readState().error).toBe("kaboom");
  });

  it("does not poll while disabled", async () => {
    const fetcher = vi.fn(async () => ({ n: 1 }));

    render(
      <Harness
        fetcher={fetcher}
        isTerminal={() => false}
        options={{ intervalMs: 5, enabled: false }}
      />,
    );

    await new Promise((r) => setTimeout(r, 30));
    expect(fetcher).not.toHaveBeenCalled();
    expect(readState().terminal).toBe(false);
  });

  it("retries until the maxMs deadline when stopOnError is false", async () => {
    let calls = 0;
    const fetcher = async () => {
      calls += 1;
      throw new Error("transient");
    };

    render(
      <Harness
        fetcher={fetcher}
        isTerminal={() => false}
        options={{
          intervalMs: 5,
          maxMs: 20,
          stopOnError: false,
          immediateFirst: true,
        }}
      />,
    );

    await waitFor(() => expect(readState().timedOut).toBe(true));
    expect(calls).toBeGreaterThan(1);
    expect(readState().error).toBe("transient");
  });
});

function SmoothHarness({
  realPct,
  active,
  etaSeconds,
}: {
  realPct: number;
  active: boolean;
  etaSeconds: number | null;
}) {
  const pct = useSmoothProgress(realPct, active, etaSeconds);
  return <div data-testid="pct">{pct}</div>;
}

function readPct() {
  return Number(screen.getByTestId("pct").textContent);
}

describe("useSmoothProgress", () => {
  it("creeps forward while active even when real progress stays at 0", async () => {
    render(<SmoothHarness realPct={0} active={true} etaSeconds={null} />);

    // Starts at 0, then eases upward on its own.
    expect(readPct()).toBe(0);
    await waitFor(() => expect(readPct()).toBeGreaterThan(0));
    // Never reaches 100 while running.
    await new Promise((r) => setTimeout(r, 50));
    expect(readPct()).toBeLessThan(100);
  });

  it("snaps to real progress on the terminal tick", async () => {
    const { rerender } = render(
      <SmoothHarness realPct={0} active={true} etaSeconds={null} />,
    );
    await waitFor(() => expect(readPct()).toBeGreaterThan(0));

    rerender(<SmoothHarness realPct={100} active={false} etaSeconds={null} />);
    await waitFor(() => expect(readPct()).toBe(100));
  });

  it("never rewinds when real progress lags the estimate", async () => {
    render(<SmoothHarness realPct={0} active={true} etaSeconds={null} />);
    await waitFor(() => expect(readPct()).toBeGreaterThan(1));
    const peak = readPct();
    // Real progress reports lower than the eased estimate — display holds.
    await new Promise((r) => setTimeout(r, 40));
    expect(readPct()).toBeGreaterThanOrEqual(peak);
  });
});
