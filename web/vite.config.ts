/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser talks only to the FastAPI backend (docs/WEB_ARCHITECTURE.md). In development the
// dev server proxies /api to it, so no CORS setup is needed; in production the web build is
// served from the same origin as the API (or LEARNABLE_PUBLIC_API_BASE_URL points at it).
const apiTarget = process.env.LEARNABLE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // Only variables with this prefix are compiled into the browser bundle, which is public.
  // Deliberately not the default VITE_: a server secret can't end up here by habit.
  envPrefix: "LEARNABLE_PUBLIC_",
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
