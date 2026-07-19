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

const AW_TAG_ID = "AW-18335528009";

// Fill this in after creating the Purchase conversion action in Google Ads.
// It looks like "AW-18335528009/AbC-dEfG12345". Leave empty to disable.
const PURCHASE_SEND_TO = "";

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
// Matches the URL-based "visit to /app" conversion configured in Google Ads,
// but gated so repeat logins by existing users don't count.
export function trackSignup(me: { id: string; created_at: string }): void {
  if (getStoredConsent() !== "granted") return;
  const created = Date.parse(me.created_at);
  if (Number.isNaN(created) || Date.now() - created > SIGNUP_FRESH_MS) return;

  let fired: string[] = [];
  try {
    fired = JSON.parse(localStorage.getItem(SIGNUP_FIRED_KEY) || "[]");
  } catch {
    /* ignore */
  }
  if (fired.includes(me.id)) return;

  adsPageview("/app");

  try {
    fired.push(me.id);
    localStorage.setItem(SIGNUP_FIRED_KEY, JSON.stringify(fired));
  } catch {
    /* ignore */
  }
}

// Fire the purchase conversion. Requires PURCHASE_SEND_TO to be set.
// valueCad is optional — the confirm endpoint doesn't return the pack value,
// so it is normally fired without a value.
export function trackPurchase(valueCad?: number): void {
  if (getStoredConsent() !== "granted" || !PURCHASE_SEND_TO) return;
  loadGtag();
  gtag("event", "conversion", {
    send_to: PURCHASE_SEND_TO,
    ...(valueCad !== undefined ? { value: valueCad, currency: "CAD" } : {}),
  });
}
