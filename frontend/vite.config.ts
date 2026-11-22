import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target:
            process.env.API_PROXY_TARGET ||
            env.API_PROXY_TARGET ||
            "http://127.0.0.1:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
    test: {
      environment: "jsdom",
      include: ["src/**/*.{test,spec}.{ts,tsx}"],
      setupFiles: "./src/test/setup.ts",
      css: true,
      restoreMocks: true,
      server: {
        deps: {
          inline: ["reshaped"],
        },
      },
    },
  };
});