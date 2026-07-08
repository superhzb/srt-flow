import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Slice 1: dev proxy /api → backend so the SPA hits same-origin in dev.
// Prod: FastAPI serves dist/ same-origin (slice 6).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5730,
    proxy: {
      "/api": {
        target: "http://localhost:5731",
        changeOrigin: true,
      },
    },
  },
});
