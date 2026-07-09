import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePoll } from "./hooks.ts";

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
