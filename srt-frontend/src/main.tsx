import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import { TranslatePage } from "./TranslatePage.tsx";
import { matchLangRoute } from "./routes.ts";
import "./index.css";

// Public marketing routes render a standalone, stateless page — no session,
// workflow, or app nav. Everything else is the app SPA.
const langRoute = matchLangRoute(window.location.pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {langRoute ? (
      <TranslatePage source={langRoute.source} target={langRoute.target} />
    ) : (
      <App />
    )}
  </StrictMode>,
);
