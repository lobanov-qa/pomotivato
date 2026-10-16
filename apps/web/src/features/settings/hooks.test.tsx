import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeSync } from "./hooks";

/**
 * ThemeSync (spec 03 ⚑ Q9 + Д1): the component mirrors the server truth to
 * <html>. Д1 adds data-skin next to data-theme — one source, two attributes.
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
  ui: {
    max_in_work: 6,
    theme: "dark",
    require_science_fields: false,
    wet_hints: true,
    done_visible_limit: 10,
    sound_enabled: true,
    signal_kind: "siren",
    skin: "modern",
  },
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(SETTINGS), {
        headers: { "content-type": "application/json" },
      })
    )
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.skin;
});

function renderSync() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ThemeSync />
    </QueryClientProvider>
  );
}

describe("ThemeSync", () => {
  it("mirrors the server theme AND skin onto <html> (Д1)", async () => {
    renderSync();

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(document.documentElement.dataset.skin).toBe("modern");
  });
});
