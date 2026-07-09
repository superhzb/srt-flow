import { useEffect, useRef, useState } from "react";

import {
  errMessage,
  getMe,
  googleLoginUrl,
  startCheckout,
  type Me,
} from "./api.ts";
import { ErrorBanner, RefreshButton, TierBadge } from "./components.tsx";
import { usePoll } from "./hooks.ts";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; me: Me | null }
  | { kind: "error"; message: string };

type CheckoutStatus = "success" | "cancel" | null;

type ConfirmationState = { kind: "confirming" } | { kind: "timeout" } | null;

interface BillingScreenProps {
  checkoutStatus?: CheckoutStatus;
  onCheckoutStatusHandled?: () => void;
}

export function BillingScreen({
  checkoutStatus = null,
  onCheckoutStatusHandled,
}: BillingScreenProps) {
  const initialCheckoutStatusRef = useRef(checkoutStatus);
  const shouldConfirm = initialCheckoutStatusRef.current === "success";
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationState>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  function refresh() {
    setState({ kind: "loading" });
    setCheckoutError(null);
    setConfirmation(null);
    setConfirmError(null);
    getMe()
      .then((me) => setState({ kind: "ready", me }))
      .catch((e: unknown) => {
        setState({
          kind: "error",
          message: errMessage(e, "failed to load billing"),
        });
      });
  }

  async function handleUpgrade() {
    setCheckoutLoading(true);
    setCheckoutError(null);
    try {
      const { url } = await startCheckout();
      window.location.href = url;
    } catch (e) {
      setCheckoutError(errMessage(e, "failed to start checkout"));
    } finally {
      setCheckoutLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    if (initialCheckoutStatusRef.current !== null) {
      onCheckoutStatusHandled?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-once intent
  }, []);

  // Payment-confirmation loop: poll /me until tier flips to paid or the 20s
  // deadline elapses. Replaces the hand-rolled setTimeout/cancelled loop (#20).
  const confirmPoll = usePoll(
    () => getMe(),
    (me) => me?.tier === "paid",
    {
      enabled: shouldConfirm,
      maxMs: 20_000,
      stopOnError: false,
      immediateFirst: true,
    },
  );

  useEffect(() => {
    if (!shouldConfirm) return;
    if (confirmPoll.result) setState({ kind: "ready", me: confirmPoll.result });
    if (confirmPoll.terminal) {
      setConfirmation(null);
    } else if (confirmPoll.timedOut) {
      setConfirmation({ kind: "timeout" });
      if (confirmPoll.error) setConfirmError(confirmPoll.error);
    } else {
      setConfirmation({ kind: "confirming" });
    }
  }, [
    confirmPoll.result,
    confirmPoll.terminal,
    confirmPoll.timedOut,
    confirmPoll.error,
    shouldConfirm,
  ]);

  return (
    <section className="mt-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Billing</h2>
          <p className="text-sm text-slate-600">Plan status and checkout.</p>
        </div>
        <RefreshButton onClick={refresh} loading={state.kind === "loading"} />
      </div>

      {state.kind === "error" && <ErrorBanner>{state.message}</ErrorBanner>}
      {checkoutError && <ErrorBanner>{checkoutError}</ErrorBanner>}
      {confirmError && <ErrorBanner>{confirmError}</ErrorBanner>}

      {confirmation?.kind === "confirming" && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800">
          Confirming your payment...
        </div>
      )}

      {confirmation?.kind === "timeout" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Payment is still processing. Click Refresh in a moment.
        </div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        {state.kind === "loading" && (
          <p className="text-sm text-slate-600">Loading...</p>
        )}

        {state.kind === "ready" && state.me === null && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold">Not authenticated</h3>
              <p className="mt-1 text-sm text-slate-600">
                Log in before opening Stripe checkout.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                window.location.href = googleLoginUrl();
              }}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
            >
              Login
            </button>
          </div>
        )}

        {state.kind === "ready" && state.me?.tier === "free" && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold">Free plan</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-slate-800">
                  {state.me.email}
                </span>
                <TierBadge tier={state.me.tier} />
              </div>
            </div>
            <button
              type="button"
              onClick={() => void handleUpgrade()}
              disabled={checkoutLoading || confirmation?.kind === "confirming"}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {confirmation?.kind === "confirming"
                ? "Confirming..."
                : checkoutLoading
                  ? "Opening..."
                  : "Upgrade"}
            </button>
          </div>
        )}

        {state.kind === "ready" && state.me?.tier === "paid" && (
          <div>
            <h3 className="font-semibold">You're on the paid plan</h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-slate-800">{state.me.email}</span>
              <TierBadge tier={state.me.tier} />
            </div>
          </div>
        )}
      </section>
    </section>
  );
}
