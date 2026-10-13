import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the FastAPI backend so the frontend can just
// call relative paths like fetch("/api/query") in both dev and prod
// (when built and served behind the same reverse proxy as the backend).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // 8081 is the local backend port; 8000 is restricted on this Windows machine.
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
      },
    },
  },
});
