import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount between tests so timers and subscriptions do not leak across cases.
afterEach(() => {
  cleanup();
});
