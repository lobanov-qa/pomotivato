/**
 * Route table for tests (spec 03 §7 testid policy). Only interactive/nav
 * surfaces get a testid; the components themselves live in later PRs.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "../components/Layout";
import Placeholder from "../components/Placeholder";

function routes() {
  return createMemoryRouter(
    [
      {
        path: "/",
        element: <Layout />,
        children: [
          { index: true, element: <Placeholder titleKey="nav.tasks" /> },
          { path: "focus", element: <Placeholder titleKey="nav.focus" /> },
          { path: "settings", element: <Placeholder titleKey="nav.settings" /> },
        ],
      },
    ],
    { initialEntries: ["/"] },
  );
}

describe("app shell", () => {
  it("renders the brand and three nav links", () => {
    render(<RouterProvider router={routes()} />);

    expect(screen.getByTestId("nav.brand")).toHaveTextContent("Pomotivato");
    expect(screen.getByTestId("nav.tasks-link")).toHaveTextContent("Задачи");
    expect(screen.getByTestId("nav.focus-link")).toHaveTextContent("Фокус");
    expect(screen.getByTestId("nav.settings-link")).toHaveTextContent("Настройки");
  });

  it("switches routes via nav clicks", async () => {
    const user = userEvent.setup();
    render(<RouterProvider router={routes()} />);

    await user.click(screen.getByTestId("nav.focus-link"));
    expect(screen.getByTestId("placeholder.root")).toHaveTextContent("Фокус");

    await user.click(screen.getByTestId("nav.settings-link"));
    expect(screen.getByTestId("placeholder.root")).toHaveTextContent("Настройки");
  });

  it("marks the current route for styling", () => {
    render(<RouterProvider router={routes()} />);

    expect(screen.getByTestId("nav.tasks-link")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("nav.focus-link")).not.toHaveAttribute("aria-current");
  });
});
