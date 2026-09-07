/**
 * The week browser contract (spec 04 §2/§4.2): read-only, kind decides the
 * body, volume bars come from the server. Drag-to-plan is E4b by law —
 * nothing here mutates anything.
 *
 * All expectations hang off the CURRENT Monday, never a hardcoded date:
 * the screen defaults to the live week, so CI runs on any day stay green.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WeekScreen } from "@/components/week/WeekScreen";
import { mondayOf } from "@/features/week/dates";

const BASE = mondayOf(new Date().toLocaleDateString("en-CA"));

function dayAt(start: string, offset: number): string {
  return new Date(Date.parse(`${start}T00:00:00Z`) + offset * 86_400_000)
    .toISOString()
    .slice(0, 10);
}

/** Any window: first cell has real work, tomorrow has the habit, rest empty. */
function weekItems(start: string) {
  return Array.from({ length: 7 }, (_, i) =>
    i === 0
      ? {
          date: start,
          weekday: 0, // start is always a Monday (BASE/shifted windows)
          kind: "past" as const,
          summary: { blocks_done: 3, focus_min: 30, average_score: 4.5, tasks_done: 2 },
          slots: [
            { sector: 1, task_id: "t-1", task_title: "Alpha", status: "doing", last_score: 4 },
            { sector: 2, task_id: "t-2", task_title: "Beta", status: "planned", last_score: null },
          ],
          planned: null,
          slots_count: null,
          volume: 3,
        }
      : {
          date: dayAt(start, i),
          weekday: i,
          kind: "future" as const,
          summary: null,
          slots: null,
          planned:
            i === 1 ? [{ task_id: "h-1", title: "Daily habit", type: "habit" as const }] : [],
          slots_count: 0,
          volume: i === 1 ? 1 : 0,
        }
  );
}

const fetchMock = vi.fn();

/** The mock window follows the requested start: prev/next/today clicks
 * must actually shift the rendered day cells. */
function mockFetch() {
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://x");
    if (url.pathname === "/api/week") {
      const start = url.searchParams.get("start") ?? BASE;
      return new Response(JSON.stringify({ start, days: 7, items: weekItems(start) }), {
        headers: { "content-type": "application/json" },
      });
    }
    return new Response("[]", { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WeekScreen />
    </QueryClientProvider>
  );
}

function lastParam(name: string): string | null {
  const url = new URL(String(fetchMock.mock.calls.at(-1)?.[0]), "http://x");
  return url.searchParams.get(name);
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("WeekScreen", () => {
  it("renders seven day cells of the current week", async () => {
    mockFetch();

    renderScreen();
    await waitFor(() => expect(screen.getByTestId(`week.day-${BASE}`)).toBeInTheDocument());

    expect(screen.getAllByTestId(/^week\.day-/)).toHaveLength(7);
    expect(lastParam("start")).toBe(BASE);
  });

  it("shows past-day truth: blocks, focus and score", async () => {
    mockFetch();

    renderScreen();
    const cell = await screen.findByTestId(`week.day-${BASE}`);

    expect(cell).toHaveTextContent("3 · 30мин");
    expect(cell).toHaveTextContent("4.5");
  });

  it("shows recurrence on the next day and the placeholder when none", async () => {
    mockFetch();

    renderScreen();
    const tomorrow = await screen.findByTestId(`week.day-${dayAt(BASE, 1)}`);

    expect(tomorrow).toHaveTextContent("Daily habit");
    expect(screen.getByTestId(`week.day-${dayAt(BASE, 6)}`)).toHaveTextContent("нет повторов");
  });

  it("opens a read-only detail panel when a day is clicked", async () => {
    mockFetch();

    renderScreen();
    await screen.findByTestId(`week.day-${BASE}`);
    await userEvent.click(screen.getByTestId(`week.day-${BASE}`));

    const detail = screen.getByTestId("week.detail");
    expect(detail).toHaveTextContent("Alpha");
    expect(detail).toHaveTextContent("Beta");
    // Read-only law: no inputs anywhere in the detail panel.
    expect(detail.querySelector("input")).toBeNull();
    expect(detail.querySelector("textarea")).toBeNull();

    await userEvent.click(screen.getByTestId("week.detail-close"));
    expect(screen.queryByTestId("week.detail")).not.toBeInTheDocument();
  });

  it("walks windows by seven days on prev/next", async () => {
    mockFetch();
    renderScreen();
    await screen.findByTestId(`week.day-${BASE}`);

    await userEvent.click(screen.getByTestId("week.next"));
    await waitFor(() =>
      expect(screen.getByTestId(`week.day-${dayAt(BASE, 7)}`)).toBeInTheDocument()
    );
    expect(lastParam("start")).toBe(dayAt(BASE, 7));

    // Back to the mount-time window: TanStack serves it from cache (no
    // refetch by design), so the contract is the DOM, not the network.
    await userEvent.click(screen.getByTestId("week.prev"));
    await waitFor(() => expect(screen.getByTestId(`week.day-${BASE}`)).toBeInTheDocument());
  });

  it("jumps back to the current week", async () => {
    mockFetch();
    renderScreen();
    await screen.findByTestId(`week.day-${BASE}`);

    await userEvent.click(screen.getByTestId("week.next"));
    await waitFor(() =>
      expect(screen.getByTestId(`week.day-${dayAt(BASE, 7)}`)).toBeInTheDocument()
    );

    await userEvent.click(screen.getByTestId("week.today"));
    await waitFor(() => expect(screen.getByTestId(`week.day-${BASE}`)).toBeInTheDocument());
  });
});
