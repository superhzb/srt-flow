import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import { ConsentBanner } from "./ConsentBanner.tsx";
import { adsPageview, initConsent } from "./consent.ts";
import { TranslatePage } from "./TranslatePage.tsx";
import { matchContentRoute } from "./contentPages.tsx";
import { matchLangRoute } from "./routes.ts";
import "./index.css";

// Public marketing + static content routes render a standalone, stateless page
// — no session, workflow, or app nav. Everything else is the app SPA.
const pathname = window.location.pathname;
const langRoute = matchLangRoute(pathname);
const contentRoute = matchContentRoute(pathname);

// Google Ads: load gtag if consent was already granted. Marketing/content pages
// are the ad landing targets — record a pageview for remarketing. The /app
// sign-up conversion is fired separately from App.tsx (see consent.ts).
initConsent();
if (langRoute || contentRoute || pathname === "/") {
  adsPageview();
}

const page = langRoute ? (
  <TranslatePage source={langRoute.source} target={langRoute.target} />
) : contentRoute ? (
  <contentRoute.Component />
) : (
  <App />
);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {page}
    <ConsentBanner />
  </StrictMode>,
);
