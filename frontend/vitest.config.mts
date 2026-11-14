import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // React only exposes `act` (and the test-friendly build) when NODE_ENV is
    // "test". An ambient NODE_ENV=production in the shell would otherwise make
    // every component test fail with "React.act is not a function".
    env: { NODE_ENV: "test" },
  },
});
