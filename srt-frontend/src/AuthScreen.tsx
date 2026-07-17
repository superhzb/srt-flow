import { useEffect, useState } from "react";

import {
  errMessage,
  getMe,
  googleLoginUrl,
  logout,
  paidCheck,
  type Me,
} from "./api.ts";
import { ErrorBanner, RefreshButton, TierBadge } from "./components.tsx";

// Discriminated unions replace the 7 ad-hoc useState values (#24), mirroring
// BillingScreen's LoadState pattern: each async flow is one state machine.
type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; me: Me | null }
  | { kind: "error"; message: string };

type TierCheckState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "result"; status: number }
  | { kind: "error"; message: string };

export function AuthScreen() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [tierCheck, setTierCheck] = useState<TierCheckState>({ kind: "idle" });
  const [loggingOut, setLoggingOut] = useState(false);

  function refreshSession() {
    setState({ kind: "loading" });
    getMe()
      .then((me) => setState({ kind: "ready", me }))
      .catch((e: unknown) =>
        setState({
          kind: "error",
          message: errMessage(e, "failed to load session"),
        }),
      );
  }

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
      setTierCheck({ kind: "idle" });
      refreshSession();
    } catch (e) {
      setState({
        kind: "error",
        message: errMessage(e, "failed to log out"),
      });
    } finally {
      setLoggingOut(false);
    }
  }

  async function handlePaidCheck() {
    setTierCheck({ kind: "checking" });
    try {
      setTierCheck({ kind: "result", status: await paidCheck() });
    } catch (e) {
      setTierCheck({
        kind: "error",
        message: errMessage(e, "failed to check tier"),
      });
    }
  }

  useEffect(() => {
    refreshSession();
  }, []);

  return (
    <section className="mt-6 space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Auth</h2>
          <p className="text-sm text-ink-muted">Session and tier checks.</p>
        </div>
        <RefreshButton
          onClick={refreshSession}
          loading={state.kind === "loading"}
        />
      </div>

      {state.kind === "error" && <ErrorBanner>{state.message}</ErrorBanner>}
      {tierCheck.kind === "error" && (
        <ErrorBanner>{tierCheck.message}</ErrorBanner>
      )}

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Session</h3>
            {state.kind === "loading" && (
              <p className="mt-1 text-sm text-ink-muted">Loading...</p>
            )}
            {state.kind === "ready" && state.me === null && (
              <p className="mt-1 text-sm text-ink-muted">
                Not authenticated (401)
              </p>
            )}
            {state.kind === "ready" && state.me && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-ink">{state.me.email}</span>
                <TierBadge tier={state.me.tier} />
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                window.location.href = googleLoginUrl();
              }}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle"
            >
              Login
            </button>
            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loggingOut ? "Logging out..." : "Logout"}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Tier Gate</h3>
            <p className="mt-1 text-sm text-ink-muted">
              GET /api/auth/paid-check
            </p>
          </div>
          <button
            type="button"
            onClick={handlePaidCheck}
            disabled={tierCheck.kind === "checking"}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-60"
          >
            {tierCheck.kind === "checking" ? "Checking..." : "Check"}
          </button>
        </div>

        {tierCheck.kind === "result" && (
          <div className="mt-3">
            <CheckBadge status={tierCheck.status} />
          </div>
        )}
      </section>
    </section>
  );
}

function CheckBadge({ status }: { status: number }) {
  if (status === 200) {
    return (
      <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-sm font-medium text-emerald-700">
        200 OK (paid)
      </span>
    );
  }
  if (status === 402) {
    return (
      <span className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-sm font-medium text-amber-800">
        402 Upgrade required
      </span>
    );
  }
  return (
    <span className="rounded-md border border-border bg-surface-subtle px-2.5 py-1 text-sm font-medium text-ink-muted">
      401 Not authenticated
    </span>
  );
}
