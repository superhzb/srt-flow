import { useEffect, useRef, useState } from "react";

import {
  errMessage,
  getBillingBalance,
  getMe,
  googleLoginUrl,
  startCheckout,
  type BillingBalance,
  type CreditPack,
  type Me,
} from "./api.ts";
import { ErrorBanner, RefreshButton } from "./components.tsx";
import { usePoll } from "./hooks.ts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; me: Me | null; balance: BillingBalance | null }
  | { kind: "error"; message: string };

type CheckoutStatus = "success" | "cancel" | null;
type ConfirmationState = { kind: "confirming" } | { kind: "timeout" } | null;

interface BillingScreenProps {
  checkoutStatus?: CheckoutStatus;
  onCheckoutStatusHandled?: () => void;
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

export function BillingScreen({
  checkoutStatus = null,
  onCheckoutStatusHandled,
}: BillingScreenProps) {
  const initialCheckoutStatusRef = useRef(checkoutStatus);
  const shouldConfirm = initialCheckoutStatusRef.current === "success";
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [openingPack, setOpeningPack] = useState<CreditPack | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationState>(null);

  function refresh() {
    setState({ kind: "loading" });
    setCheckoutError(null);
    Promise.all([getMe(), getBillingBalance().catch(() => null)])
      .then(([me, balance]) => setState({ kind: "ready", me, balance }))
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
    try {
      const { url } = await startCheckout(pack);
      window.location.href = url;
    } catch (error) {
      setCheckoutError(errMessage(error, "failed to start checkout"));
      setOpeningPack(null);
    }
  }

  useEffect(() => {
    refresh();
    if (initialCheckoutStatusRef.current !== null) onCheckoutStatusHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-once intent
  }, []);

  const confirmPoll = usePoll(
    () => getBillingBalance(),
    () => true,
    {
      enabled: shouldConfirm,
      maxMs: 20_000,
      stopOnError: false,
      immediateFirst: true,
    },
  );

  useEffect(() => {
    if (!shouldConfirm) return;
    if (confirmPoll.result) {
      getMe().then((me) =>
        setState({ kind: "ready", me, balance: confirmPoll.result }),
      );
    }
    if (confirmPoll.terminal) setConfirmation(null);
    else if (confirmPoll.timedOut) setConfirmation({ kind: "timeout" });
    else setConfirmation({ kind: "confirming" });
  }, [
    confirmPoll.result,
    confirmPoll.terminal,
    confirmPoll.timedOut,
    shouldConfirm,
  ]);

  return (
    <section className="mt-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Minutes & billing</h2>
          <p className="text-sm text-ink-muted">
            Monthly free minutes plus non-expiring packs.
          </p>
        </div>
        <RefreshButton onClick={refresh} loading={state.kind === "loading"} />
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
        <section className="rounded-lg border border-border bg-surface p-4">
          <h3 className="font-semibold">Sign in to buy minutes</h3>
          <button
            type="button"
            onClick={() => (window.location.href = googleLoginUrl())}
            className="mt-3 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white"
          >
            Continue with Google
          </button>
        </section>
      )}

      {state.kind === "ready" &&
        state.me !== null &&
        state.balance !== null && (
          <>
            <section className="rounded-lg border border-border bg-surface p-5">
              <p className="text-sm text-ink-muted">Available now</p>
              <p className="mt-1 text-4xl font-semibold gradient-text">
                {state.balance.available_minutes} min
              </p>
              <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div className="rounded-md bg-surface-subtle p-3">
                  Free this month: {state.balance.free_remaining} /{" "}
                  {state.balance.free_limit} min
                </div>
                <div className="rounded-md bg-surface-subtle p-3">
                  Purchased balance: {state.balance.purchased_minutes} min
                </div>
              </div>
            </section>
            <div className="grid gap-4 md:grid-cols-2">
              {packs.map((pack) => (
                <section
                  key={pack.id}
                  className={`rounded-lg border bg-surface p-5 ${pack.id === "large" ? "border-accent" : "border-border"}`}
                >
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
                </section>
              ))}
            </div>
            <p className="text-center text-xs text-ink-muted">
              One-time payment · no subscription · purchased minutes do not
              expire
            </p>
          </>
        )}
    </section>
  );
}
