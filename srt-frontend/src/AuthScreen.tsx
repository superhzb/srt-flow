import { useEffect, useState } from "react";

import {
  getMe,
  googleLoginUrl,
  logout,
  paidCheck,
  type Me,
} from "./api.ts";

type CheckStatus = 200 | 401 | 402 | null;

export function AuthScreen() {
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [checkingTier, setCheckingTier] = useState(false);
  const [checkStatus, setCheckStatus] = useState<CheckStatus>(null);

  function refreshSession() {
    setLoadingSession(true);
    setError(null);
    getMe()
      .then((nextMe) => {
        setMe(nextMe);
        setLoaded(true);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "failed to load session");
      })
      .finally(() => {
        setLoadingSession(false);
      });
  }

  async function handleLogout() {
    setLoggingOut(true);
    setError(null);
    try {
      await logout();
      setCheckStatus(null);
      refreshSession();
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to log out");
    } finally {
      setLoggingOut(false);
    }
  }

  async function handlePaidCheck() {
    setCheckingTier(true);
    setError(null);
    try {
      setCheckStatus((await paidCheck()) as CheckStatus);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to check tier");
    } finally {
      setCheckingTier(false);
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
          <p className="text-sm text-slate-600">Session and tier checks.</p>
        </div>
        <button
          type="button"
          onClick={refreshSession}
          disabled={loadingSession}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loadingSession ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Session</h3>
            {!loaded && !error && (
              <p className="mt-1 text-sm text-slate-600">Loading...</p>
            )}
            {loaded && me === null && (
              <p className="mt-1 text-sm text-slate-600">
                Not authenticated (401)
              </p>
            )}
            {me && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-slate-800">{me.email}</span>
                <TierBadge tier={me.tier} />
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                window.location.href = googleLoginUrl();
              }}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
            >
              Login
            </button>
            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loggingOut ? "Logging out..." : "Logout"}
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold">Tier Gate</h3>
            <p className="mt-1 text-sm text-slate-600">
              GET /api/auth/paid-check
            </p>
          </div>
          <button
            type="button"
            onClick={handlePaidCheck}
            disabled={checkingTier}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {checkingTier ? "Checking..." : "Check"}
          </button>
        </div>

        {checkStatus !== null && (
          <div className="mt-3">
            <CheckBadge status={checkStatus} />
          </div>
        )}
      </section>
    </section>
  );
}

function TierBadge({ tier }: { tier: Me["tier"] }) {
  const classes =
    tier === "paid"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-slate-200 bg-slate-50 text-slate-700";

  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${classes}`}>
      {tier}
    </span>
  );
}

function CheckBadge({ status }: { status: Exclude<CheckStatus, null> }) {
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
    <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-sm font-medium text-slate-700">
      401 Not authenticated
    </span>
  );
}
