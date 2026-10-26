import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest does not expose a global afterEach by default. Explicit cleanup
// prevents DOM trees from earlier tests leaking into later role queries.
afterEach(() => {
  cleanup();
});
