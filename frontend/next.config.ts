import type { NextConfig } from "next";

const isProduction = process.env.NODE_ENV === "production";

/**
 * Security headers applied to every response.
 *
 * The Content-Security-Policy is deliberately explicit rather than "unsafe-*":
 * Next needs `'unsafe-inline'` for its bootstrap script and for the style
 * attributes Tailwind emits, but scripts themselves are otherwise same-origin
 * only. `connect-src` stays `'self'` because all backend traffic goes through
 * the BFF proxy on this origin — the browser never talks to FastAPI directly.
 */
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isProduction ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "geolocation=(), microphone=(), camera=(), interest-cohort=()",
  },
];

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,

  // `poweredByHeader: false` removes the `X-Powered-By: Next.js` fingerprint.
  poweredByHeader: false,

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },

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
