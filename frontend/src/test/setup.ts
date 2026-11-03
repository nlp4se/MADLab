import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom does not implement ResizeObserver, which React Flow (the designer
// canvas) instantiates on mount. Provide a no-op polyfill so components that
// render the canvas (e.g. the smoke e2e) don't crash in jsdom.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver =
    ResizeObserverStub as unknown as typeof ResizeObserver;
}

// jsdom lacks the DOMMatrix / matchMedia APIs React Flow touches during layout;
// stub the minimum it reads so the canvas mounts without throwing.
if (typeof globalThis.DOMMatrixReadOnly === "undefined") {
  class DOMMatrixStub {
    m22 = 1;
    constructor(_transform?: string) {}
  }
  globalThis.DOMMatrixReadOnly =
    DOMMatrixStub as unknown as typeof DOMMatrixReadOnly;
}

// Unmount React trees after every test to keep the jsdom DOM isolated.
afterEach(() => {
  cleanup();
});
