/**
 * The dashboard contract (spec 04 §2/§5): numbers come pre-baked from the
 * server, sections render only with data, empty state for a fresh DB.
 * echarts is mocked (no canvas in jsdom) — widget presence is asserted on
 * the host divs; option math is covered by chartOptions.test.ts (pure).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StatsDto } from "@/api/client";

import { StatsScreen } from "./StatsScreen";

vi.mock("echarts", () => ({
  init: () => ({
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
  }),
}));

function statsFixture(overrides: Partial<StatsDto> = {}): StatsDto {
  return {
    period: { from: "2026-08-09", to: "2026-09-07" },
    totals: {
      blocks_done: 9,
      focus_min: 108,
      average_score: 3.5,
      reviews_count: 2,
      tasks_done: 1,
      tasks_total: 8,
    },
    heatmap: [{ date: "2026-09-06", blocks_done: 9, focus_min: 108 }],
    streak: {
      current: 1,
      current_started: "2026-09-06",
      record: 1,
      record_started: "2026-09-06",
    },
    estimate_vs_fact: {
      ratio: 1.5,
      points: [{ task_id: "t-1", title: "Alpha", estimate: 2, actual: 3 }],
    },
    quadrants: [
      { key: "important_urgent", tasks_done: 1, blocks: 3, average_score: 4 },
      { key: "important_not_urgent", tasks_done: 0, blocks: 0, average_score: null },
      { key: "urgent_not_important", tasks_done: 0, blocks: 0, average_score: null },
      { key: "neither", tasks_done: 0, blocks: 0, average_score: null },
    ],
    goal_depth: [
      { filled_fields: 0, tasks: 8, done_ratio: 0.1 },
      { filled_fields: 1, tasks: 0, done_ratio: 0 },
      { filled_fields: 2, tasks: 0, done_ratio: 0 },
      { filled_fields: 3, tasks: 0, done_ratio: 0 },
    ],
    parents: [{ task_id: "p-1", title: "Big goal", done_children: 1, total_children: 3 }],
    zombies: { count: 1, items: [{ task_id: "t-7", title: "Stuck frog", days_stuck: 10 }] },
    ...overrides,
  };
}

const fetchMock = vi.fn();

function mockFetch(fixture: StatsDto) {
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/api/stats")) {
      return new Response(JSON.stringify(fixture), {
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
      <StatsScreen />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("StatsScreen", () => {
  it("renders totals, streak and ratio from the server snapshot", async () => {
    mockFetch(statsFixture());

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.stat-blocks")).toBeInTheDocument());

    expect(screen.getByTestId("stats.stat-blocks")).toHaveTextContent("9");
    expect(screen.getByTestId("stats.stat-score")).toHaveTextContent("3.5");
    expect(screen.getByTestId("stats.streak-current")).toHaveTextContent("1");
    expect(screen.getByTestId("stats.streak-record")).toHaveTextContent("1");
    expect(screen.getByTestId("stats.ratio")).toHaveTextContent("1.5");
  });

  it("mounts a chart host per widget", async () => {
    mockFetch(statsFixture());

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.widget-heatmap")).toBeInTheDocument());

    expect(screen.getByTestId("stats.widget-estimate")).toBeInTheDocument();
    expect(screen.getByTestId("stats.widget-quadrants")).toBeInTheDocument();
    expect(screen.getByTestId("stats.widget-goal-depth")).toBeInTheDocument();
  });

  it("renders parents and zombies lists with server truth", async () => {
    mockFetch(statsFixture());

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.parent-p-1")).toBeInTheDocument());

    expect(screen.getByTestId("stats.parent-p-1")).toHaveTextContent("Big goal");
    expect(screen.getByTestId("stats.parent-p-1")).toHaveTextContent("1/3");
    expect(screen.getByTestId("stats.zombie-t-7")).toHaveTextContent("Stuck frog");
    expect(screen.getByTestId("stats.zombie-t-7")).toHaveTextContent("10");
  });

  it("hides parents and zombies sections when the server sends none", async () => {
    mockFetch(statsFixture({ parents: [], zombies: { count: 0, items: [] } }));

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.stat-blocks")).toBeInTheDocument());

    expect(screen.queryByTestId("stats.parent-p-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("stats.zombie-t-7")).not.toBeInTheDocument();
  });

  it("answers the empty state for a fresh database", async () => {
    mockFetch(
      statsFixture({
        totals: {
          blocks_done: 0,
          focus_min: 0,
          average_score: null,
          reviews_count: 0,
          tasks_done: 0,
          tasks_total: 0,
        },
        heatmap: [],
        parents: [],
        estimate_vs_fact: { ratio: null, points: [] },
      })
    );

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.empty")).toBeInTheDocument());

    expect(screen.queryByTestId("stats.stat-blocks")).not.toBeInTheDocument();
  });

  it("refetches with explicit period params on toggle", async () => {
    mockFetch(statsFixture());

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.stat-blocks")).toBeInTheDocument());

    const before = fetchMock.mock.calls.length;
    await userEvent.click(screen.getByTestId("stats.period-week"));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));

    const last = fetchMock.mock.calls.at(-1)?.[0] as string;
    expect(last).toContain("/api/stats");
    expect(last).toContain("from=");
    expect(last).toContain("to=");
  });

  it("renders the em-dash when the period has no reviews", async () => {
    mockFetch(
      statsFixture({
        totals: {
          blocks_done: 0,
          focus_min: 0,
          average_score: null,
          reviews_count: 0,
          tasks_done: 0,
          tasks_total: 3,
        },
        heatmap: [],
        parents: [],
        estimate_vs_fact: { ratio: null, points: [] },
      })
    );

    renderScreen();
    await waitFor(() => expect(screen.getByTestId("stats.stat-score")).toBeInTheDocument());

    expect(screen.getByTestId("stats.stat-score")).toHaveTextContent("—");
  });
});
