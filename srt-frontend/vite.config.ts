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
    port: Number(process.env.FRONTEND_PORT) || 19105,
    allowedHosts: ["www.srt-flow.com", ".srt-flow.com"],
    proxy: {
      "/api": {
        target: `http://localhost:${process.env.BACKEND_PORT || 19205}`,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
});
