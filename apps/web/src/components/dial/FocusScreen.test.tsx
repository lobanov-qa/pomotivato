import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionDto, TaskDto } from "@/api/client";
import { FocusScreen } from "./FocusScreen";

/**
 * The dial screen contract (spec 03 §2): NO task editing controls, the
 * hand is driven by server truth, lifecycle buttons follow the FSM state.
 * EventSource is stubbed; fetch answers /api/status + /api/tasks + GET
 * session so the whole data path is real code.
 */

class FakeSource {
  static instances: FakeSource[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>();
  closed = false;
  constructor(public url: string) {
    FakeSource.instances.push(this);
    // Real servers answer every connection with a snapshot frame (spec 03 §4).
    queueMicrotask(() => {
      if (!this.closed) this.emit("snapshot", current);
    });
  }
  addEventListener(type: string, fn: EventListener): void {
    this.listeners.set(type, fn as (event: MessageEvent) => void);
  }
  close(): void {
    this.closed = true;
  }
  emit(type: string, data: unknown): void {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

const TASKS: TaskDto[] = [
  {
    id: "t-1",
    title: "Deep work",
    type: "normal",
    important: true,
    urgent: false,
    status: "doing",
    estimate_blocks: 2,
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    created_at: "2026-09-06T09:00:00+00:00",
  },
];

function session(overrides: Partial<SessionDto> = {}): SessionDto {
  return {
    id: "s-1",
    day_plan_id: "p-1",
    state: "running",
    started_at: "2026-09-06T09:00:00+00:00",
    stop_reason: null,
    phase: "work",
    remaining_sec: 600,
    phase_ends_at: "2026-09-06T09:10:00+00:00",
    average_score: null,
    settings: {
      work_min: 10,
      break_min: 5,
      long_break_min: 15,
      long_break_every: 4,
      auto_start_next: true,
    },
    timeline: [
      {
        id: "s-1-0",
        session_id: "s-1",
        phase: "work",
        planned_min: 10,
        task_id: "t-1",
        started_at: "2026-09-06T09:00:00+00:00",
        ended_at: null,
        status: null,
      },
    ],
    reviews: [],
    slots: [
      { sector: 1, task_id: "t-1" },
      { sector: 2, task_id: "t-1" },
    ],
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let current: SessionDto | null;

beforeEach(() => {
  FakeSource.instances = [];
  current = session();
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const json = (status: number, body: unknown) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      });
    if (url.startsWith("/api/status")) {
      return json(200, {
        active: Boolean(current),
        session_id: current?.id ?? null,
        state: current?.state ?? null,
        phase: current?.phase ?? null,
        remaining_sec: current?.remaining_sec ?? null,
        server_now: "2026-09-06T09:00:00+00:00",
        date: "2026-09-06",
      });
    }
    if (url.startsWith("/api/tasks")) return json(200, TASKS);
    if (url.startsWith("/api/sessions/s-1") && (!init?.method || init.method === "GET")) {
      return json(200, current);
    }
    if (url.includes("/pause") && current) {
      current = session({ state: "paused" });
      return json(200, current);
    }
    if (url.includes("/resume") && current) {
      current = session({ state: "running" });
      return json(200, current);
    }
    if (url.startsWith("/api/day-plans")) return json(404, { detail: { code: "not_found" } });
    return json(404, { detail: { code: "not_found", message: url } });
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", FakeSource);
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
      <FocusScreen />
    </QueryClientProvider>,
  );
}

describe("FocusScreen", () => {
  it("renders the dial with sectors from the session snapshot", async () => {
    renderScreen();

    expect(await screen.findByTestId("dial.sector-2")).toBeInTheDocument();
    expect(screen.getByTestId("dial.sector-1")).toBeInTheDocument();
    expect(screen.queryByTestId("dial.sector-3")).not.toBeInTheDocument();
    expect(screen.getByTestId("dial.time-readout")).toHaveTextContent("10:00");
  });

  it("is read-only for tasks: no inputs, no edit controls", async () => {
    renderScreen();
    await screen.findByTestId("dial.pause-button"); // session is live

    expect(screen.queryByTestId(/task-card\./)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    // funnel law: doing == the dial; sector names live in the legend only
    expect(screen.getByTestId("dial.legend-item-1")).toHaveTextContent("Deep work");
  });

  it("shows the full task name outside the circle and the sector legend", async () => {
    renderScreen();
    await screen.findByTestId("dial.task-name"); // session is live

    // author's law 2026-09-06: no text on the dial, the name lives below
    expect(screen.getByTestId("dial.task-name")).toHaveTextContent("Deep work");
    expect(screen.getByTestId("dial.legend")).toBeInTheDocument();
    expect(screen.getByTestId("dial.legend-item-1")).toHaveTextContent("Deep work");
    expect(screen.getByTestId("dial.legend-item-2")).toHaveTextContent("Deep work");
    const texts = document.querySelectorAll("svg text");
    expect(texts).toHaveLength(1); // only the time readout
  });

  it("pause freezes the readout and offers resume", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByTestId("dial.pause-button"));

    await waitFor(() => expect(screen.getByTestId("dial.resume-button")).toBeInTheDocument());
    expect(screen.getByTestId("dial.paused-hint")).toBeInTheDocument();
    expect(screen.getByTestId("dial.time-readout")).toHaveTextContent("10:00");
  });

  it("subscribes to the SSE stream of the active session", async () => {
    renderScreen();
    await waitFor(() => expect(FakeSource.instances).toHaveLength(1));
    expect(FakeSource.instances[0].url).toBe("/api/sessions/s-1/events");

    FakeSource.instances[0].emit("snapshot", session({ remaining_sec: 300 }));
    await waitFor(() => expect(screen.getByTestId("dial.time-readout")).toHaveTextContent("5:00"));
  });

  it("refetches the full view on phase_changed (hand/rim need the new segment)", async () => {
    renderScreen();
    await waitFor(() => expect(FakeSource.instances).toHaveLength(1));
    const getsBefore = fetchMock.mock.calls.filter(
      ([url, init]) => String(url).startsWith("/api/sessions/s-1") && (!init || init.method === "GET"),
    ).length;

    FakeSource.instances[0].emit("phase_changed", {
      phase: "break",
      segment_id: "s-1-1",
      ends_at: "2026-09-06T09:15:00+00:00",
      remaining_sec: 300,
    });

    await waitFor(() => {
      const gets = fetchMock.mock.calls.filter(
        ([url, init]) =>
          String(url).startsWith("/api/sessions/s-1") && (!init || init.method === "GET"),
      ).length;
      expect(gets).toBeGreaterThan(getsBefore);
    });
  });
});
