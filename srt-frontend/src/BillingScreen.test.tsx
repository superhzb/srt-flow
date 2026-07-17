import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getBillingBalance,
  getBillingConfirm,
  getBillingHistory,
  getMe,
  type BillingHistoryPage,
  type BillingTransaction,
} from "./api.ts";
import { BillingScreen } from "./BillingScreen.tsx";

vi.mock("./api.ts", async () => {
  const actual = await vi.importActual<typeof import("./api.ts")>("./api.ts");
  return {
    ...actual,
    getMe: vi.fn(),
    getBillingBalance: vi.fn(),
    getBillingHistory: vi.fn(),
    getBillingConfirm: vi.fn(),
    startCheckout: vi.fn(),
  };
});

const me = {
  id: "acct_123456789",
  email: "person@example.com",
  tier: "free" as const,
  is_admin: false,
  created_at: "2025-02-03T00:00:00+00:00",
};

const balance = {
  free_limit: 20,
  free_used: 5,
  free_remaining: 15,
  purchased_minutes: 100,
  available_minutes: 115,
};

function transaction(
  id: string,
  overrides: Partial<BillingTransaction> = {},
): BillingTransaction {
  return {
    id,
    created_at: new Date().toISOString(),
    entry_type: "purchase",
    minutes_delta: 100,
    usage_minutes: 0,
    balance_after: 100,
    pack: "small",
    amount_cents: 399,
    currency: "usd",
    reason: "Stripe Checkout purchase",
    receipt_url: null,
    ...overrides,
  };
}

function page(
  entries: BillingTransaction[],
  overrides: Partial<BillingHistoryPage> = {},
): BillingHistoryPage {
  return { entries, has_more: false, next_cursor: null, ...overrides };
}

beforeEach(() => {
  vi.mocked(getMe).mockResolvedValue(me);
  vi.mocked(getBillingBalance).mockResolvedValue(balance);
  vi.mocked(getBillingConfirm).mockResolvedValue({ applied: false });
  vi.mocked(getBillingHistory).mockResolvedValue(page([]));
});

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("BillingScreen", () => {
  it("renders account, usage, ledger minutes, and receipt details", async () => {
    vi.mocked(getBillingHistory).mockResolvedValue(
      page([
        transaction("purchase", {
          receipt_url: "https://pay.example/receipt",
        }),
        transaction("usage", {
          entry_type: "job_debit",
          minutes_delta: -3,
          usage_minutes: 7,
          amount_cents: null,
          currency: null,
          reason: "Translation job",
        }),
      ]),
    );

    render(<BillingScreen />);

    expect(await screen.findByText("person@example.com")).toBeInTheDocument();
    expect(screen.getByText("115 min")).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Total credit remaining",
      }),
    ).toHaveAttribute("aria-valuenow", "115");
    expect(screen.getByText("−3 min")).toBeInTheDocument();
    expect(
      screen.getByText("Translation — 7 min, 3 charged to credit"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View receipt" })).toHaveAttribute(
      "href",
      "https://pay.example/receipt",
    );
  });

  it("appends cursor pages and replaces rows when the server filter changes", async () => {
    vi.mocked(getBillingHistory)
      .mockResolvedValueOnce(
        page([transaction("first", { reason: "First purchase" })], {
          has_more: true,
          next_cursor: "cursor-1",
        }),
      )
      .mockResolvedValueOnce(
        page([transaction("second", { reason: "Older purchase" })]),
      )
      .mockResolvedValueOnce(
        page([
          transaction("usage-only", {
            entry_type: "job_debit",
            minutes_delta: -2,
            usage_minutes: 4,
            amount_cents: null,
            currency: null,
            reason: "Filtered usage",
          }),
        ]),
      );

    render(<BillingScreen />);
    expect(await screen.findByText("First purchase")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Older purchase")).toBeInTheDocument();
    expect(getBillingHistory).toHaveBeenNthCalledWith(2, {
      before: "cursor-1",
      category: "purchases",
    });

    fireEvent.change(
      screen.getByRole("combobox", { name: "Transaction type" }),
      {
        target: { value: "all" },
      },
    );
    expect(
      await screen.findByText("Translation — 4 min, 2 charged to credit"),
    ).toBeInTheDocument();
    expect(screen.queryByText("First purchase")).not.toBeInTheDocument();
    expect(screen.queryByText("Older purchase")).not.toBeInTheDocument();
    expect(getBillingHistory).toHaveBeenNthCalledWith(3, { category: "all" });
  });

  it("polls the returned checkout session and refreshes balance and history", async () => {
    vi.mocked(getBillingConfirm).mockResolvedValue({ applied: true });
    vi.mocked(getBillingHistory)
      .mockResolvedValueOnce(page([]))
      .mockResolvedValueOnce(
        page([transaction("confirmed", { reason: "Confirmed purchase" })]),
      );

    render(
      <BillingScreen
        checkoutStatus="success"
        checkoutSessionId="cs_returned"
      />,
    );

    expect(await screen.findByText("Confirmed purchase")).toBeInTheDocument();
    expect(getBillingConfirm).toHaveBeenCalledWith("cs_returned");
    expect(getBillingBalance).toHaveBeenCalledTimes(2);
    expect(getBillingHistory).toHaveBeenCalledTimes(2);
  });

  it("shows a timeout when a checkout session is not applied", async () => {
    vi.useFakeTimers();
    render(
      <BillingScreen checkoutStatus="success" checkoutSessionId="cs_pending" />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(21_000);
    });

    expect(screen.getByText(/Payment is still processing/)).toBeInTheDocument();
    expect(getBillingConfirm).toHaveBeenCalledWith("cs_pending");
  });
});
