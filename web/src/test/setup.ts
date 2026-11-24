import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, vi } from "vitest";
import { loadAllCatalogs } from "../i18n";

beforeAll(() => loadAllCatalogs());

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});
