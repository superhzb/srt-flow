import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

declare const process: {
  env: {
    BACKEND_PORT?: string;
    FRONTEND_PORT?: string;
  };
};

// Slice 1: dev proxy /api → backend so the SPA hits same-origin in dev.
// Prod: FastAPI serves dist/ same-origin (slice 6).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: Number(process.env.FRONTEND_PORT) || 19105,
    allowedHosts: ["www.srt-flow.com", ".srt-flow.com"],
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || 19205}`,
        changeOrigin: true,
      },
      // No changeOrigin: SQLAdmin builds every link with request.url_for(),
      // which is absolute and derived from the Host header. Rewriting Host to
      // the backend target makes those links point at 127.0.0.1:<backend>, a
      // different origin than the browser's, so the srt_session cookie isn't
      // sent and every admin navigation bounces to the login redirect.
      "/admin": {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT || 19205}`,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
});
