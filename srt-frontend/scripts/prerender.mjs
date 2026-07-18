// Build-time prerender: render every public route to static HTML so crawlers
// and social scrapers see real content (the SPA still hydrates on top). Run
// after `vite build` — see package.json "build". Also emits sitemap.xml.
//
// Uses Vite's programmatic SSR (ssrLoadModule) — no headless browser, no extra
// runtime dependency. Renders src/prerender-entry.tsx per URL from src/routes.ts.

import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

const template = await readFile(join(dist, "index.html"), "utf8");
if (!template.includes("<!-- seo:start")) {
  throw new Error("index.html is missing the <!-- seo:start --> marker block");
}
if (!template.includes('<div id="root"></div>')) {
  throw new Error('index.html is missing <div id="root"></div>');
}

const vite = await createServer({
  root,
  appType: "custom",
  logLevel: "warn",
  server: { middlewareMode: true },
});

try {
  const { renderRoute } = await vite.ssrLoadModule("/src/prerender-entry.tsx");
  const { PUBLIC_ROUTES } = await vite.ssrLoadModule("/src/routes.ts");
  const { SITE_URL } = await vite.ssrLoadModule("/src/seo.ts");

  for (const route of PUBLIC_ROUTES) {
    const { appHtml, headTags } = renderRoute(route);
    const html = template
      .replace(
        /<!-- seo:start[\s\S]*?<!-- seo:end -->/,
        `<!-- seo:start -->\n    ${headTags}\n    <!-- seo:end -->`,
      )
      .replace('<div id="root"></div>', `<div id="root">${appHtml}</div>`);

    // "/" → dist/index.html ; "/translate/x" → dist/translate/x/index.html
    const outPath =
      route === "/"
        ? join(dist, "index.html")
        : join(dist, route.replace(/^\//, ""), "index.html");
    await mkdir(dirname(outPath), { recursive: true });
    await writeFile(outPath, html, "utf8");
    console.log(`prerendered ${route} -> ${outPath.slice(dist.length + 1)}`);
  }

  const urls = PUBLIC_ROUTES.map((route) => {
    const loc = `${SITE_URL}${route === "/" ? "/" : route}`;
    const priority = route === "/" ? "1.0" : "0.8";
    return `  <url>\n    <loc>${loc}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>${priority}</priority>\n  </url>`;
  }).join("\n");
  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
  await writeFile(join(dist, "sitemap.xml"), sitemap, "utf8");
  console.log(`wrote sitemap.xml (${PUBLIC_ROUTES.length} urls)`);
} finally {
  await vite.close();
}
