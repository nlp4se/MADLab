import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { NAV_ITEMS } from "@/routes";
import { AppLayout } from "./AppLayout";

/** Task 11.15: the sidebar without the Dimensions legend; a content column that can't overflow. */
function renderLayout() {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ path: "configs", element: <p>content</p> }] }],
    { initialEntries: ["/configs"] },
  );
  render(<RouterProvider router={router} />);
}

describe("AppLayout (task 11.15)", () => {
  it("has no Dimensions legend in the sidebar", () => {
    renderLayout();
    expect(screen.queryByText("Dimensions")).not.toBeInTheDocument();
    // The legend's dimension labels are gone too (nav labels are unaffected).
    expect(screen.queryByText("Participants")).not.toBeInTheDocument();
    expect(screen.queryByText("Agreement")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Configurations/ })).toBeInTheDocument();
  });

  it("links Designer to /designer (a new, unsaved configuration)", () => {
    renderLayout();
    expect(screen.getByRole("link", { name: /Designer/ })).toHaveAttribute("href", "/designer");
    // One route with an optional id serves both `/designer` and `/designer/<id>`.
    expect(NAV_ITEMS.find((i) => i.label === "Designer")?.routePath).toBe(
      "/designer/:configId?",
    );
  });

  it("keeps the content column from growing past the viewport", () => {
    renderLayout();
    const main = screen.getByRole("main");
    expect(main).toHaveClass("min-w-0", "flex-1", "overflow-auto");
    expect(main).toHaveTextContent("content");
  });
});
