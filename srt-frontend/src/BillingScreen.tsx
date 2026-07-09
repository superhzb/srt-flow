import { useEffect, useRef, useState } from "react";

import { getMe, googleLoginUrl, startCheckout, type Me } from "./api.ts";

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
  const onCheckoutStatusHandledRef = useRef(onCheckoutStatusHandled);
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationState>(null);

  function refresh() {
    setState({ kind: "loading" });
    setCheckoutError(null);
    setConfirmation(null);
    getMe()
      .then((me) => setState({ kind: "ready", me }))
      .catch((e: unknown) => {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "failed to load billing",
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
      setCheckoutError(e instanceof Error ? e.message : "failed to start checkout");
    } finally {
      setCheckoutLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    const initialCheckoutStatus = initialCheckoutStatusRef.current;
    if (initialCheckoutStatus === null) return;
    onCheckoutStatusHandledRef.current?.();
    if (initialCheckoutStatus === "cancel") return;

    let cancelled = false;
    let timeoutId: number | undefined = undefined;
    const deadline = Date.now() + 20_000;

    setCheckoutError(null);
    setConfirmation({ kind: "confirming" });

    function poll() {
      getMe()
        .then((me) => {
          if (cancelled) return;
          setState({ kind: "ready", me });
          if (me?.tier === "paid") {
            setConfirmation(null);
            return;
          }
          if (Date.now() >= deadline) {
            setConfirmation({ kind: "timeout" });
            return;
          }
          timeoutId = window.setTimeout(poll, 1500);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          if (Date.now() >= deadline) {
            setConfirmation({ kind: "timeout" });
            setState({
              kind: "error",
              message: e instanceof Error ? e.message : "failed to confirm payment",
            });
            return;
          }
          timeoutId = window.setTimeout(poll, 1500);
        });
    }

    poll();

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, []);

  return (
    <section className="mt-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Billing</h2>
          <p className="text-sm text-slate-600">Plan status and checkout.</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={state.kind === "loading"}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {state.kind === "loading" ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {state.kind === "error" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {state.message}
        </div>
      )}

      {checkoutError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {checkoutError}
        </div>
      )}

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
                <span className="font-mono text-slate-800">{state.me.email}</span>
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

function TierBadge({ tier }: { tier: Me["tier"] }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
        tier === "paid"
          ? "bg-emerald-100 text-emerald-700"
          : "bg-slate-100 text-slate-700"
      }`}
    >
      {tier}
    </span>
  );
}
