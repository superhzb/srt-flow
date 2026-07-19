import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import { TranslatePage } from "./TranslatePage.tsx";
import { matchContentRoute } from "./contentPages.tsx";
import { matchLangRoute } from "./routes.ts";
import "./index.css";

// Public marketing + static content routes render a standalone, stateless page
// — no session, workflow, or app nav. Everything else is the app SPA.
const pathname = window.location.pathname;
const langRoute = matchLangRoute(pathname);
const contentRoute = matchContentRoute(pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {langRoute ? (
      <TranslatePage source={langRoute.source} target={langRoute.target} />
    ) : contentRoute ? (
      <contentRoute.Component />
    ) : (
      <App />
    )}
  </StrictMode>,
);
