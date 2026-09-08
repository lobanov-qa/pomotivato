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
    strict_mode: false,
    warmup_min: 0,
    special_breaks: [],
  },
  ui: { max_in_work: 6, theme: "auto" as const, require_science_fields: false },
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

  it("modes section: strict flip + warm-up clamp land in the session PUT", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("settings.switch-strict");

    await user.click(screen.getByTestId("settings.switch-strict"));
    await typeNumber(screen.getByTestId("settings.field-warmup_min"), "99");

    expect(screen.getByTestId("settings.switch-strict")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("settings.field-warmup_min")).toHaveValue(30); // V12 clamp
    await user.click(screen.getByTestId("settings.save"));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts.find((x) => x.url === "/api/settings/session")?.body).toMatchObject({
      strict_mode: true,
      warmup_min: 30,
    });
  });

  it("special-breaks editor adds and removes rows through the draft", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("settings.special-break-add");

    await user.click(screen.getByTestId("settings.special-break-add"));

    expect(screen.getByTestId("settings.special-break-0")).toBeInTheDocument();
    await user.click(screen.getByTestId("settings.special-break-0-remove"));
    expect(screen.queryByTestId("settings.special-break-0")).not.toBeInTheDocument();
    // removed the row again -> back to pristine: save stays disabled
    expect(screen.getByTestId("settings.save")).toBeDisabled();
  });

  it("require-science switch rides the ui PUT (V8 gate)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("settings.switch-require-science");

    await user.click(screen.getByTestId("settings.switch-require-science"));
    await user.click(screen.getByTestId("settings.save"));

    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts.find((x) => x.url === "/api/settings/ui")?.body).toMatchObject({
      require_science_fields: true,
    });
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
