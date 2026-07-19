import { useEffect, useState } from "react";

import { getStoredConsent, grantConsent, denyConsent } from "./consent.ts";

// Cookie-consent banner for Google Ads (Consent Mode v2). Shows only until the
// user makes a choice; choice persists in localStorage. Until accepted, no
// third-party ad/analytics storage is set.
export function ConsentBanner() {
  const [decided, setDecided] = useState(true);

  // Read consent after mount so prerendered HTML never bakes in the banner.
  useEffect(() => {
    setDecided(getStoredConsent() !== null);
  }, []);

  if (decided) return null;

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      className="fixed inset-x-0 bottom-0 z-[60] border-t border-black/10 bg-surface p-4 shadow-2xl dark:border-white/10"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-muted">
          We use Google Ads cookies to measure the effectiveness of our
          advertising. They load only if you accept. See our{" "}
          <a href="/privacy" className="underline">
            Privacy Policy
          </a>
          .
        </p>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={() => {
              denyConsent();
              setDecided(true);
            }}
            className="rounded-lg border border-black/15 px-4 py-2 text-sm font-medium dark:border-white/20"
          >
            Decline
          </button>
          <button
            onClick={() => {
              grantConsent();
              setDecided(true);
            }}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-surface"
          >
            Accept
          </button>
        </div>
      </div>
    </div>
  );
}
