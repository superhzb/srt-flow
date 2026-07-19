import { useEffect, useRef, useState } from "react";

import {
  errMessage,
  getBillingBalance,
  getBillingConfirm,
  getBillingHistory,
  getMe,
  googleLoginUrl,
  startCheckout,
  type BillingBalance,
  type BillingCategory,
  type BillingHistoryPage,
  type BillingTransaction,
  type CreditPack,
  type Me,
} from "./api.ts";
import {
  ErrorBanner,
  QuotaBar,
  RefreshButton,
  TierBadge,
} from "./components.tsx";
import { trackPurchase } from "./consent.ts";
import { usePoll } from "./hooks.ts";
import { formatCurrency, formatLedgerDate } from "./lib.ts";
import { Card } from "./ui.tsx";
import { track } from "./analytics.ts";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ready";
      me: Me | null;
      balance: BillingBalance | null;
      history: BillingHistoryPage | null;
    }
  | { kind: "error"; message: string };

type CheckoutStatus = "success" | "cancel" | null;
type ConfirmationState = { kind: "confirming" } | { kind: "timeout" } | null;

interface BillingScreenProps {
  checkoutStatus?: CheckoutStatus;
  checkoutSessionId?: string | null;
  onCheckoutStatusHandled?: () => void;
  onLogout?: () => void;
}

const packs: Array<{
  id: CreditPack;
  name: string;
  price: string;
  minutes: number;
  unit: string;
}> = [
  {
    id: "small",
    name: "Small pack",
    price: "$3.99",
    minutes: 100,
    unit: "$0.040/min",
  },
  {
    id: "large",
    name: "Large pack",
    price: "$29.99",
    minutes: 1000,
    unit: "$0.030/min",
  },
];

// USD pack prices, for Google Ads purchase-conversion revenue attribution.
const PACK_USD: Record<CreditPack, number> = { small: 3.99, large: 29.99 };

const historyFilters: Array<{ value: BillingCategory; label: string }> = [
  { value: "purchases", label: "Purchases" },
  { value: "all", label: "All" },
  { value: "adjustments", label: "Adjustments" },
];

export function BillingScreen({
  checkoutStatus = null,
  checkoutSessionId = null,
  onCheckoutStatusHandled,
  onLogout,
}: BillingScreenProps) {
  const initialCheckoutStatusRef = useRef(checkoutStatus);
  const initialSessionIdRef = useRef(checkoutSessionId);
  const shouldConfirm =
    initialCheckoutStatusRef.current === "success" &&
    initialSessionIdRef.current !== null;
  const refreshedAfterConfirmation = useRef(false);
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [category, setCategory] = useState<BillingCategory>("purchases");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [openingPack, setOpeningPack] = useState<CreditPack | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationState>(null);

  function refresh(nextCategory: BillingCategory = category) {
    setState({ kind: "loading" });
    setCheckoutError(null);
    setHistoryError(null);
    getMe()
      .then(async (me) => {
        if (me === null) {
          setState({ kind: "ready", me, balance: null, history: null });
          return;
        }
        const [balance, history] = await Promise.all([
          getBillingBalance(),
          getBillingHistory({ category: nextCategory }),
        ]);
        setState({ kind: "ready", me, balance, history });
      })
      .catch((error: unknown) =>
        setState({
          kind: "error",
          message: errMessage(error, "failed to load billing"),
        }),
      );
  }

  async function handleCheckout(pack: CreditPack) {
    setOpeningPack(pack);
    setCheckoutError(null);
    track("cta_clicked", { cta: `buy_${pack}` });
    try {
      const { url } = await startCheckout(pack);
      // Stash the purchase value (USD) so the post-Stripe confirm page can
      // attribute revenue to the Google Ads conversion.
      try {
        localStorage.setItem("pending_purchase_usd", String(PACK_USD[pack]));
      } catch {
        /* storage unavailable */
      }
      window.location.href = url;
    } catch (error) {
      setCheckoutError(errMessage(error, "failed to start checkout"));
      setOpeningPack(null);
    }
  }

  async function changeCategory(nextCategory: BillingCategory) {
    setCategory(nextCategory);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const history = await getBillingHistory({ category: nextCategory });
      setState((current) =>
        current.kind === "ready" ? { ...current, history } : current,
      );
    } catch (error) {
      setHistoryError(errMessage(error, "failed to load billing history"));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadMore() {
    if (state.kind !== "ready" || !state.history?.next_cursor) return;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const page = await getBillingHistory({
        before: state.history.next_cursor,
        category,
      });
      setState((current) => {
        if (current.kind !== "ready" || current.history === null)
          return current;
        return {
          ...current,
          history: {
            ...page,
            entries: [...current.history.entries, ...page.entries],
          },
        };
      });
    } catch (error) {
      setHistoryError(errMessage(error, "failed to load billing history"));
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    refresh("purchases");
    if (initialCheckoutStatusRef.current !== null) onCheckoutStatusHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-once intent
  }, []);

  const confirmPoll = usePoll(
    () => getBillingConfirm(initialSessionIdRef.current!),
    (result) => result.applied,
    {
      enabled: shouldConfirm,
      maxMs: 20_000,
      stopOnError: false,
      immediateFirst: true,
    },
  );

  useEffect(() => {
    if (!shouldConfirm) return;
    if (confirmPoll.result?.applied && !refreshedAfterConfirmation.current) {
      refreshedAfterConfirmation.current = true;
      let value: number | undefined;
      try {
        const raw = localStorage.getItem("pending_purchase_usd");
        if (raw) value = Number(raw);
        localStorage.removeItem("pending_purchase_usd");
      } catch {
        /* storage unavailable */
      }
      trackPurchase(Number.isFinite(value) ? value : undefined);
      setConfirmation(null);
      refresh(category);
      return;
    }
    if (confirmPoll.timedOut) setConfirmation({ kind: "timeout" });
    else setConfirmation({ kind: "confirming" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh only on poll transitions
  }, [confirmPoll.result, confirmPoll.timedOut, shouldConfirm]);

  return (
    <section className="mt-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Billing & account</h1>
          <p className="text-sm text-ink-muted">
            Manage your account, minutes, and payment history.
          </p>
        </div>
        <RefreshButton
          onClick={() => refresh()}
          loading={state.kind === "loading"}
        />
      </div>

      {state.kind === "error" && <ErrorBanner>{state.message}</ErrorBanner>}
      {checkoutError && <ErrorBanner>{checkoutError}</ErrorBanner>}
      {confirmation?.kind === "confirming" && (
        <div className="rounded-lg border border-accent bg-accent-soft p-3 text-sm text-accent-deep">
          Confirming your payment…
        </div>
      )}
      {confirmation?.kind === "timeout" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Payment is still processing. Refresh again in a moment.
        </div>
      )}

      {state.kind === "loading" && (
        <p className="text-sm text-ink-muted">Loading…</p>
      )}
      {state.kind === "ready" && state.me === null && (
        <Card className="p-5">
          <h2 className="font-semibold">Sign in to manage billing</h2>
          <button
            type="button"
            onClick={() => (window.location.href = googleLoginUrl())}
            className="mt-3 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white"
          >
            Continue with Google
          </button>
        </Card>
      )}

      {state.kind === "ready" && state.me && state.balance && state.history && (
        <>
          <AccountCard
            me={state.me}
            balance={state.balance}
            onLogout={onLogout}
          />
          <UsageCard balance={state.balance} />

          <section aria-labelledby="buy-minutes-heading">
            <div className="mb-3">
              <h2 id="buy-minutes-heading" className="text-lg font-semibold">
                Buy minutes
              </h2>
              <p className="text-sm text-ink-muted">
                One-time packs that never expire.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {packs.map((pack) => (
                <Card key={pack.id} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">{pack.name}</h3>
                      <p className="mt-2 text-3xl font-semibold">
                        {pack.price}
                      </p>
                      <p className="text-sm text-ink-muted">
                        {pack.minutes} min · {pack.unit}
                      </p>
                    </div>
                    {pack.id === "large" && (
                      <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">
                        Best value
                      </span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleCheckout(pack.id)}
                    disabled={openingPack !== null}
                    className="mt-5 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                  >
                    {openingPack === pack.id
                      ? "Opening…"
                      : `Buy ${pack.minutes} min`}
                  </button>
                </Card>
              ))}
            </div>
          </section>

          <HistoryTable
            history={state.history}
            category={category}
            loading={historyLoading}
            error={historyError}
            onCategoryChange={(next) => void changeCategory(next)}
            onLoadMore={() => void loadMore()}
          />
        </>
      )}
    </section>
  );
}

function AccountCard({
  me,
  balance,
  onLogout,
}: {
  me: Me;
  balance: BillingBalance;
  onLogout?: () => void;
}) {
  const memberSince = new Date(me.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  // Effective tier reflects purchased credit: "paid" while credit remains,
  // reverts to the account tier once purchased minutes are exhausted.
  const effectiveTier: "free" | "paid" =
    balance.purchased_minutes > 0 ? "paid" : me.tier;
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">
            Account
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">{me.email}</h2>
            <TierBadge tier={effectiveTier} />
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            Member since {memberSince}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {onLogout && (
            <button
              type="button"
              onClick={onLogout}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
            >
              Logout
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}

function UsageCard({ balance }: { balance: BillingBalance }) {
  // Total credit pool = monthly free allowance + purchased minutes. The bar
  // shows how much of that pool remains (available), not just the free bucket.
  const total = balance.free_limit + balance.purchased_minutes;
  const used = Math.max(0, total - balance.available_minutes);
  return (
    <Card className="p-5">
      <p className="text-sm text-ink-muted">Available now</p>
      <p className="mt-1 text-4xl font-semibold gradient-text">
        {balance.available_minutes} min
      </p>
      <div className="mt-5 rounded-lg bg-surface-subtle p-4">
        <QuotaBar
          used={used}
          limit={total}
          label="Credit"
          ariaLabel="Total credit remaining"
        />
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-lg bg-surface-subtle p-3">
          <span className="block text-xs text-ink-muted">Free this month</span>
          {balance.free_remaining} / {balance.free_limit} min
        </div>
        <div className="rounded-lg bg-surface-subtle p-3">
          <span className="block text-xs text-ink-muted">
            Purchased balance
          </span>
          {balance.purchased_minutes} min
        </div>
      </div>
    </Card>
  );
}

function HistoryTable({
  history,
  category,
  loading,
  error,
  onCategoryChange,
  onLoadMore,
}: {
  history: BillingHistoryPage;
  category: BillingCategory;
  loading: boolean;
  error: string | null;
  onCategoryChange: (category: BillingCategory) => void;
  onLoadMore: () => void;
}) {
  return (
    <section aria-labelledby="billing-history-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="billing-history-heading" className="text-lg font-semibold">
            Billing history
          </h2>
          <p className="text-sm text-ink-muted">
            Purchases and adjustments. Usage lives in History.
          </p>
        </div>
        <label className="text-xs text-ink-muted">
          <span className="mr-2">Type</span>
          <select
            aria-label="Transaction type"
            value={category}
            onChange={(event) =>
              onCategoryChange(event.target.value as BillingCategory)
            }
            disabled={loading}
            className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink"
          >
            {historyFilters.map((filter) => (
              <option key={filter.value} value={filter.value}>
                {filter.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      <Card className="overflow-hidden">
        {history.entries.length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-ink-muted">
            No transactions yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-border bg-surface-subtle text-xs text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Description</th>
                  <th className="px-4 py-3 text-right font-medium">
                    Minutes (±)
                  </th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                  <th className="px-4 py-3 text-right font-medium">Receipt</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {history.entries.map((entry) => (
                  <HistoryRow key={entry.id} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {history.has_more && (
          <div className="border-t border-border px-4 py-3 text-center">
            <button
              type="button"
              onClick={onLoadMore}
              disabled={loading}
              className="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-subtle disabled:opacity-60"
            >
              {loading ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </Card>
    </section>
  );
}

function HistoryRow({ entry }: { entry: BillingTransaction }) {
  const minutes = entry.minutes_delta;
  const amount =
    entry.amount_cents !== null && entry.currency
      ? formatCurrency(entry.amount_cents, entry.currency)
      : "—";
  return (
    <tr>
      <td className="whitespace-nowrap px-4 py-3 text-ink-muted">
        {formatLedgerDate(entry.created_at)}
      </td>
      <td className="px-4 py-3">
        <span className="rounded-full bg-surface-subtle px-2 py-1 text-xs text-ink-muted">
          {entryTypeLabel(entry.entry_type)}
        </span>
      </td>
      <td className="max-w-xs px-4 py-3">{entryDescription(entry)}</td>
      <td
        className={`whitespace-nowrap px-4 py-3 text-right font-mono ${minutes > 0 ? "text-emerald-600" : "text-ink"}`}
      >
        {formatMinutes(minutes)}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-right">{amount}</td>
      <td className="whitespace-nowrap px-4 py-3 text-right">
        {entry.receipt_url ? (
          <a
            href={entry.receipt_url}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-accent hover:underline"
          >
            View receipt
          </a>
        ) : (
          <span className="text-ink-muted">—</span>
        )}
      </td>
    </tr>
  );
}

function entryTypeLabel(entryType: BillingTransaction["entry_type"]): string {
  if (entryType === "job_debit") return "Usage";
  if (entryType === "purchase") return "Purchase";
  if (entryType === "dispute_reinstated") return "Reinstated";
  return entryType[0].toUpperCase() + entryType.slice(1);
}

function entryDescription(entry: BillingTransaction): string {
  if (entry.entry_type === "job_debit") {
    return `Translation — ${entry.usage_minutes} min, ${Math.abs(entry.minutes_delta)} charged to credit`;
  }
  if (entry.reason) return entry.reason;
  if (entry.entry_type === "purchase") {
    return `${entry.pack ?? "Credit"} minute pack`;
  }
  if (entry.entry_type === "dispute_reinstated")
    return "Dispute funds reinstated";
  return entryTypeLabel(entry.entry_type);
}

function formatMinutes(minutes: number): string {
  if (minutes > 0) return `+${minutes} min`;
  if (minutes < 0) return `−${Math.abs(minutes)} min`;
  return "0 min";
}
