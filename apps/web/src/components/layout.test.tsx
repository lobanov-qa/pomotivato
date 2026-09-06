import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Layout from "../components/Layout";

/**
 * Route table for tests (spec 03 §7 testid policy). Only interactive/nav
 * surfaces get a testid; screens themselves are stubs here — the shell is
 * under test, real screens own their tests (kanban/dial/settings).
 */

function Stub({ id }: { id: string }) {
  return <div data-testid={id} />;
}

function routes() {
  return createMemoryRouter(
    [
      {
        path: "/",
        element: <Layout />,
        children: [
          { index: true, element: <Stub id="stub.tasks" /> },
          { path: "focus", element: <Stub id="stub.focus" /> },
          { path: "settings", element: <Stub id="stub.settings" /> },
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
    expect(screen.getByTestId("stub.focus")).toBeInTheDocument();

    await user.click(screen.getByTestId("nav.settings-link"));
    expect(screen.getByTestId("stub.settings")).toBeInTheDocument();
  });

  it("marks the current route for styling", () => {
    render(<RouterProvider router={routes()} />);

    expect(screen.getByTestId("nav.tasks-link")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("nav.focus-link")).not.toHaveAttribute("aria-current");
  });
});
