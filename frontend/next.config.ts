import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,

  // Type checking is a separate, explicit gate (`pnpm typecheck`).
  //
  // The bundled TypeScript compiler intermittently dies with a native access
  // violation (0xC0000005) on this Windows/Node 26 setup, which Next reports as
  // "Failed to type check." and turns into a failed build. The same sources pass
  // `tsc --noEmit` cleanly (verified), so this in-build check produces no signal
  // here — only flaky builds. CI must run `pnpm typecheck` before `pnpm build`.
  typescript: { ignoreBuildErrors: true },

  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
