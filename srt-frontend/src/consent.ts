// Google Ads (gtag) with Consent Mode v2.
//
// Privacy stance: the third-party gtag.js script is NOT loaded until the user
// explicitly grants consent via the banner. Consent Mode defaults are set to
// "denied" in index.html before anything runs, so Google receives no ad/
// analytics storage until opt-in. If the user declines, gtag.js never loads.
//
// Conversions:
//   - Sign up  -> URL-based conversion in Google Ads (page visit to /app).
//                 We emit that page_view only for a genuinely new account
//                 (see trackSignup) so repeat logins don't inflate it.
//   - Purchase -> explicit conversion event; needs PURCHASE_SEND_TO filled in
//                 after the "Purchase" conversion action is created in Ads.

const AW_TAG_ID = "AW-1492365021";

// Purchase conversion action (Google Ads event snippet send_to). Empty disables.
const PURCHASE_SEND_TO = "AW-1492365021/ruOhCLyYg9McEMnoh6dE";

// Sign-up conversion action (Google Ads event snippet send_to). Empty disables.
const SIGNUP_SEND_TO = "AW-1492365021/BomlCLGPmNMcEMnoh6dE";

export const CONSENT_KEY = "ads_consent"; // "granted" | "denied"
const SIGNUP_FIRED_KEY = "ads_signup_fired"; // JSON array of user ids
const SIGNUP_FRESH_MS = 5 * 60_000; // treat account as "new" if created < 5m ago

type Consent = "granted" | "denied";

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

let gtagScriptLoaded = false;

function gtag(...args: unknown[]): void {
  // window.gtag is defined inline in index.html (pushes to dataLayer).
  window.gtag?.(...args);
}

export function getStoredConsent(): Consent | null {
  try {
    const v = localStorage.getItem(CONSENT_KEY);
    return v === "granted" || v === "denied" ? v : null;
  } catch {
    return null;
  }
}

function loadGtag(): void {
  if (gtagScriptLoaded) return;
  gtagScriptLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${AW_TAG_ID}`;
  document.head.appendChild(s);
  gtag("js", new Date());
  gtag("config", AW_TAG_ID);
}

const GRANTED = {
  ad_storage: "granted",
  ad_user_data: "granted",
  ad_personalization: "granted",
  analytics_storage: "granted",
} as const;

const DENIED = {
  ad_storage: "denied",
  ad_user_data: "denied",
  ad_personalization: "denied",
  analytics_storage: "denied",
} as const;

// Call once on app boot. Loads gtag only if consent was previously granted.
export function initConsent(): void {
  if (getStoredConsent() === "granted") {
    gtag("consent", "update", GRANTED);
    loadGtag();
  }
}

export function grantConsent(): void {
  try {
    localStorage.setItem(CONSENT_KEY, "granted");
  } catch {
    /* storage unavailable */
  }
  gtag("consent", "update", GRANTED);
  loadGtag();
}

export function denyConsent(): void {
  try {
    localStorage.setItem(CONSENT_KEY, "denied");
  } catch {
    /* storage unavailable */
  }
  gtag("consent", "update", DENIED);
}

// Record a page_view (remarketing + URL-based conversions). No-op without consent.
export function adsPageview(pagePath?: string): void {
  if (getStoredConsent() !== "granted") return;
  loadGtag();
  gtag("event", "page_view", {
    page_location:
      window.location.origin + (pagePath ?? window.location.pathname),
  });
}

// Fire the sign-up conversion exactly once for a freshly created account.
// Fires the explicit Google Ads "Sign up" conversion event, gated so repeat
// logins by existing users don't count.
export function trackSignup(me: { id: string; created_at: string }): void {
  if (getStoredConsent() !== "granted" || !SIGNUP_SEND_TO) return;
  const created = Date.parse(me.created_at);
  if (Number.isNaN(created) || Date.now() - created > SIGNUP_FRESH_MS) return;

  let fired: string[] = [];
  try {
    fired = JSON.parse(localStorage.getItem(SIGNUP_FIRED_KEY) || "[]");
  } catch {
    /* ignore */
  }
  if (fired.includes(me.id)) return;

  loadGtag();
  gtag("event", "conversion", { send_to: SIGNUP_SEND_TO });

  try {
    fired.push(me.id);
    localStorage.setItem(SIGNUP_FIRED_KEY, JSON.stringify(fired));
  } catch {
    /* ignore */
  }
}

// Fire the purchase conversion. Requires PURCHASE_SEND_TO to be set.
// value/currency are optional — pass them for ROAS attribution when the
// purchased amount is known.
export function trackPurchase(value?: number, currency = "USD"): void {
  if (getStoredConsent() !== "granted" || !PURCHASE_SEND_TO) return;
  loadGtag();
  gtag("event", "conversion", {
    send_to: PURCHASE_SEND_TO,
    ...(value !== undefined ? { value, currency } : {}),
  });
}
