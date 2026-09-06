import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsScreen } from "./SettingsScreen";

/**
 * Settings screen (spec 03 §2): draft form — save is disabled until the
 * draft differs from the server, saving PUTs both keys, and the theme
 * radio writes html[data-theme] through ThemeSync's source of truth.
 */

const SETTINGS = {
  session: {
    work_min: 25,
    break_min: 5,
    long_break_min: 15,
    long_break_every: 4,
    auto_start_next: true,
  },
  ui: { max_in_work: 6, theme: "auto" as const },
};

let fetchMock: ReturnType<typeof vi.fn>;
let puts: { url: string; body: unknown }[];

beforeEach(() => {
  puts = [];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const json = (status: number, body: unknown) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    if (url === "/api/settings" && (!init?.method || init.method === "GET")) {
      return json(200, SETTINGS);
    }
    if (url.startsWith("/api/settings/") && init?.method === "PUT") {
      puts.push({ url, body: JSON.parse(String(init.body)) });
      return json(200, JSON.parse(String(init.body)));
    }
    return json(404, { detail: { code: "not_found", message: url } });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SettingsScreen />
    </QueryClientProvider>,
  );
}

// Controlled number input: set the value natively and fire `input` —
// userEvent typing appends to the clamped draft (Ctrl+A is not real
// selection in jsdom), which fights the field's own clamp logic.
async function typeNumber(element: HTMLElement, value: string): Promise<void> {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  setter.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("SettingsScreen", () => {
  it("loads server values into the draft", async () => {
    renderScreen();

    const work = await screen.findByTestId("settings.field-work_min");
    expect(work).toHaveValue(25);
    expect(screen.getByTestId("settings.field-max_in_work")).toHaveValue(6);
    expect(screen.getByTestId("settings.save")).toBeDisabled(); // nothing dirty
  });

  it("enables save after an edit and PUTs both keys", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("settings.field-work_min");

    await typeNumber(screen.getByTestId("settings.field-work_min"), "30");
    await user.click(screen.getByTestId("settings.theme-dark"));

    expect(screen.getByTestId("settings.save")).toBeEnabled();
    await user.click(screen.getByTestId("settings.save"));

    await waitFor(() => expect(puts).toHaveLength(2));
    const sessionPut = puts.find((p) => p.url === "/api/settings/session");
    const uiPut = puts.find((p) => p.url === "/api/settings/ui");
    expect(sessionPut?.body).toMatchObject({ work_min: 30 });
    expect(uiPut?.body).toMatchObject({ max_in_work: 6, theme: "dark" });
  });

  it("clamps out-of-range input to the field bounds", async () => {
    renderScreen();
    await screen.findByTestId("settings.field-work_min");

    await typeNumber(screen.getByTestId("settings.field-work_min"), "500");

    expect(screen.getByTestId("settings.field-work_min")).toHaveValue(120);
  });

  it("toggles auto_start_next via the switch", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("settings.switch-auto-start");

    await user.click(screen.getByTestId("settings.switch-auto-start"));
    expect(screen.getByTestId("settings.switch-auto-start")).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});
