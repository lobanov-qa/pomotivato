/**
 * The week screen (spec 04 §4.2 read-only browser + spec 05 §3.8 planning):
 * kind decides the body, volume bars come from the server. E4b-UX DF1 took
 * the drag strip away: the day panel now manages its slots directly —
 * reorder arrows and a × per slot — while past days (⚑ Q4) stay untouchable.
 *
 * All expectations hang off the CURRENT Monday/today, never a hardcoded
 * date: CI stays green any day of the week.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WeekScreen } from "@/components/week/WeekScreen";
import { mondayOf } from "@/features/week/dates";

const TODAY_ISO = new Date().toLocaleDateString("en-CA");
const BASE = mondayOf(TODAY_ISO);

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
          slots: SLOTS,
          planned: null,
          slots_count: null,
          volume: 3,
        }
      : {
          date: dayAt(start, i),
          weekday: i,
          kind: "future" as const,
          summary: null,
          planned:
            i === 1 ? [{ task_id: "h-1", title: "Daily habit", type: "study" as const }] : [],
          // E4b: future days carry their real slots too (planning surface).
          // The planning day is TODAY itself — a fixed BASE+1 rots after
          // midnight and makes the editable (>= today) gate flaky (DF1).
          slots: dayAt(start, i) === TODAY_ISO ? SLOTS.slice(0, 2) : [],
          slots_count: dayAt(start, i) === TODAY_ISO ? 2 : 0,
          volume: dayAt(start, i) === TODAY_ISO ? 3 : 0,
        }
  );
}

const SLOTS = [
  { sector: 1, task_id: "t-1", task_title: "Alpha", status: "doing", last_score: 4 },
  { sector: 2, task_id: "t-2", task_title: "Beta", status: "planned", last_score: null },
];

const fetchMock = vi.fn();

/** The mock window follows the requested start: prev/next/today clicks
 * must actually shift the rendered day cells. */
const STRIP_TASK = {
  id: "new-1",
  title: "Fresh idea",
  type: "normal",
  important: false,
  urgent: false,
  status: "backlog",
  estimate_blocks: 1,
  recurrence: { kind: "once" },
  deadline: null,
  parent_id: null,
  when_then: null,
  done_criteria: null,
  benefit: null,
  cloned_from: null,
  no_timer: false,
  blocks_done: null,
  created_at: "2026-09-06T09:00:00+00:00",
};

let posted: { url: string; body: unknown }[];

function mockFetch() {
  posted = [];
  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://x");
    if (url.pathname === "/api/week") {
      const start = url.searchParams.get("start") ?? BASE;
      return new Response(JSON.stringify({ start, days: 7, items: weekItems(start) }), {
        headers: { "content-type": "application/json" },
      });
    }
    if (url.pathname === "/api/tasks") {
      return new Response(JSON.stringify([STRIP_TASK]), {
        headers: { "content-type": "application/json" },
      });
    }
    if (url.pathname === "/api/repetitions/due") {
      return new Response(
        JSON.stringify([
          { task_id: "d-1", title: "Chapter 3", interval_idx: 1, next_due: "2026-09-06", overdue_days: 2 },
        ]),
        { headers: { "content-type": "application/json" } },
      );
    }
    if (url.pathname.endsWith("/add")) {
      posted.push({ url: url.pathname, body: JSON.parse(String(init?.body)) });
      return new Response(
        JSON.stringify({ plan: { id: "p", date: "x", slots: [] }, added: ["d-1"], skipped: [] }),
        { headers: { "content-type": "application/json" } },
      );
    }
    if (url.pathname.endsWith("/activate")) {
      posted.push({ url: url.pathname, body: init?.body });
      return new Response(
        JSON.stringify({ plan: { id: "p", date: "x", slots: [] }, added: ["h-1"], skipped: [] }),
        { headers: { "content-type": "application/json" } },
      );
    }
    if (/\/slots\/\d+$/.test(url.pathname) && init?.method === "DELETE") {
      posted.push({ url: url.pathname, body: null });
      return new Response(JSON.stringify({ id: "p", date: "x", slots: [] }), {
        headers: { "content-type": "application/json" },
      });
    }
    if (url.pathname.endsWith("/slots/move")) {
      posted.push({ url: url.pathname, body: JSON.parse(String(init?.body)) });
      return new Response(JSON.stringify({ id: "p", date: "x", slots: [] }), {
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
  // The screen also fetches /api/tasks and /api/sprints; the window
  // contract concerns only the last /api/week call.
  const call = [...fetchMock.mock.calls]
    .reverse()
    .find(([input]) => new URL(String(input), "http://x").pathname === "/api/week");
  if (!call) return null;
  return new URL(String(call[0]), "http://x").searchParams.get(name);
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

  it("opens a detail panel with the task law holding: forms never live here", async () => {
    mockFetch();

    renderScreen();
    await screen.findByTestId(`week.day-${TODAY_ISO}`);
    await userEvent.click(screen.getByTestId(`week.day-${TODAY_ISO}`));

    const detail = screen.getByTestId("week.detail");
    expect(detail).toHaveTextContent("Alpha");
    expect(detail).toHaveTextContent("Beta");
    // Editing a task is kanban-only: no inputs/textareas, only order arrows
    // (buttons) — the E3 screen-law extended to the planning surface.
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

  it("activation button posts to today and flashes the honest outcome", async () => {
    mockFetch();
    const todayIso = new Date().toLocaleDateString("en-CA");

    renderScreen();
    await screen.findByTestId("week.activate-today");
    await userEvent.click(screen.getByTestId("week.activate-today"));

    await waitFor(() =>
      expect(posted.some((x) => x.url === `/api/day-plans/${todayIso}/activate`)).toBe(true)
    );
    expect(await screen.findByTestId("week.flash")).toHaveTextContent("Повторы добавлены");
  });

  it("detail arrows reorder the plan via slots/move (insert semantics)", async () => {
    mockFetch();

    renderScreen();
    await screen.findByTestId(`week.day-${TODAY_ISO}`);
    await userEvent.click(screen.getByTestId(`week.day-${TODAY_ISO}`));

    // sector 1 is first: "up" is disabled, "down" moves position 1 -> 2
    expect(screen.getByTestId("week.slot-move-up-1")).toBeDisabled();
    await userEvent.click(screen.getByTestId("week.slot-move-down-1"));

    await waitFor(() =>
      expect(posted.some((x) => x.url.endsWith("/slots/move") && JSON.stringify(x.body) === '{"from":1,"to":2}')).toBe(
        true
      )
    );
  });

  it("detail × takes the slot off the day via DELETE (DF1)", async () => {
    mockFetch();

    renderScreen();
    await userEvent.click(await screen.findByTestId(`week.day-${TODAY_ISO}`));

    await userEvent.click(screen.getByTestId("week.slot-remove-1"));

    await waitFor(() =>
      expect(posted.some((x) => x.url.endsWith("/day-plans/" + TODAY_ISO + "/slots/1"))).toBe(
        true,
      )
    );
  });

  it("renders the sprint band with a create affordance when no sprint exists", async () => {
    mockFetch();

    renderScreen();
    await screen.findByTestId("week.sprint-band");

    expect(screen.getByTestId("week.sprint-band")).toHaveTextContent("Спринта нет");
    expect(screen.getByTestId("week.sprint-create")).toBeInTheDocument();
  });

  it("due queue renders rows, overdue days and plans via the add primitive", async () => {
    mockFetch();
    renderScreen();
    const section = await screen.findByTestId("week.due-section");

    expect(section).toHaveTextContent("Chapter 3");
    expect(screen.getByTestId("week.due-row-d-1")).toHaveTextContent("просрочено на 2");
    expect(screen.getByTestId("week.due-row-d-1")).toHaveTextContent("шаг 2/5");

    await userEvent.click(screen.getByTestId("week.due-add-d-1"));

    await waitFor(() =>
      expect(posted.some((x) => x.url.endsWith("/add") && JSON.stringify(x.body) === '{"task_id":"d-1"}')).toBe(
        true
      )
    );
    expect(await screen.findByTestId("week.due-flash")).toHaveTextContent("добавлено в план");
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
