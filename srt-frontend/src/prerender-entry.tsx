// Build-time SSR entry. scripts/prerender.mjs loads this via Vite's
// ssrLoadModule and calls renderRoute() for each public URL, then bakes the
// returned HTML + head tags into that route's static index.html.
//
// The client uses createRoot().render (not hydrateRoot), so this markup is
// replaced on load — it exists purely for crawlers and social scrapers, which
// means no hydration-mismatch constraints apply here.

import { renderToStaticMarkup } from "react-dom/server";

import { LandingScreen } from "./LandingScreen.tsx";
import { TranslatePage } from "./TranslatePage.tsx";
import { matchContentRoute } from "./contentPages.tsx";
import { matchLangRoute } from "./routes.ts";
import { HOME_META, metaTagsHtml, translateMeta } from "./seo.ts";

export type Rendered = { appHtml: string; headTags: string };

export function renderRoute(pathname: string): Rendered {
  const langRoute = matchLangRoute(pathname);
  if (langRoute) {
    return {
      appHtml: renderToStaticMarkup(
        <TranslatePage source={langRoute.source} target={langRoute.target} />,
      ),
      headTags: metaTagsHtml(translateMeta(langRoute.source, langRoute.target)),
    };
  }
  const contentRoute = matchContentRoute(pathname);
  if (contentRoute) {
    return {
      appHtml: renderToStaticMarkup(<contentRoute.Component />),
      headTags: metaTagsHtml(contentRoute.meta),
    };
  }
  // Home ("/") and any other prerendered path fall back to the landing page.
  return {
    appHtml: renderToStaticMarkup(<LandingScreen signedIn={false} />),
    headTags: metaTagsHtml(HOME_META),
  };
}
