import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionDto, TaskDto } from "@/api/client";
import { FocusScreen } from "./FocusScreen";

/**
 * The review flow on /focus (spec 03 §2): a closed work segment without a
 * review opens the modal; submitting POSTs /api/reviews and the modal
 * closes; "Позже" hides it until the NEXT block closes.
 */

class FakeSource {
  static instances: FakeSource[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>();
  closed = false;
  constructor(public url: string) {
    FakeSource.instances.push(this);
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
    important: false,
    urgent: false,
    status: "doing",
    estimate_blocks: 1,
    recurrence: { kind: "once" },
    deadline: null,
    parent_id: null,
    when_then: null,
    done_criteria: null,
    benefit: null,
    created_at: "2026-09-06T09:00:00+00:00",
  },
];

const CLOSED_WORK = {
  id: "s-1-0",
  session_id: "s-1",
  phase: "work",
  planned_min: 10,
  task_id: "t-1",
  started_at: "2026-09-06T09:00:00+00:00",
  ended_at: "2026-09-06T09:10:00+00:00",
  status: "completed",
};

function session(overrides: Partial<SessionDto> = {}): SessionDto {
  return {
    id: "s-1",
    day_plan_id: "p-1",
    state: "running",
    started_at: "2026-09-06T09:00:00+00:00",
    stop_reason: null,
    phase: "break",
    remaining_sec: 300,
    phase_ends_at: "2026-09-06T09:15:00+00:00",
    average_score: null,
    settings: {
      work_min: 10,
      break_min: 5,
      long_break_min: 15,
      long_break_every: 4,
      auto_start_next: true,
    },
    // first block CLOSED, second open: the review is pending
    timeline: [
      CLOSED_WORK,
      {
        id: "s-1-1",
        session_id: "s-1",
        phase: "break",
        planned_min: 5,
        task_id: null,
        started_at: "2026-09-06T09:10:00+00:00",
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
let current: SessionDto;
let reviewBodies: string[];

beforeEach(() => {
  FakeSource.instances = [];
  reviewBodies = [];
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
        active: true,
        session_id: current.id,
        state: current.state,
        phase: current.phase,
        remaining_sec: current.remaining_sec,
        server_now: "2026-09-06T09:12:00+00:00",
        date: "2026-09-06",
      });
    }
    if (url.startsWith("/api/tasks")) return json(200, TASKS);
    if (url === "/api/reviews" && init?.method === "POST") {
      reviewBodies.push(String(init.body));
      current = session({
        reviews: [{ segment_id: CLOSED_WORK.id, score: 4, comment: null }],
        average_score: 4,
      });
      return json(201, { segment_id: CLOSED_WORK.id, score: 4, comment: null });
    }
    if (url.startsWith("/api/sessions/s-1")) return json(200, current);
    if (url.startsWith("/api/summary")) {
      return json(200, {
        date: "2026-09-06",
        blocks_done: 1,
        blocks_planned: 2,
        focus_min: 10,
        average_score: null,
        reviews_count: 0,
        tasks_done: 0,
      });
    }
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

describe("review flow on /focus", () => {
  it("opens the modal for a closed work segment without a review", async () => {
    renderScreen();

    expect(await screen.findByTestId("review.modal")).toBeInTheDocument();
    expect(screen.getByTestId("review.task")).toHaveTextContent("Deep work");
  });

  it("submit posts /api/reviews and closes the modal", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("review.modal");

    await user.click(screen.getByTestId("review.scale-4"));
    await user.click(screen.getByTestId("review.submit"));

    await waitFor(() => expect(reviewBodies).toHaveLength(1));
    const body = JSON.parse(reviewBodies[0]);
    expect(body).toMatchObject({ segment_id: CLOSED_WORK.id, score: 4 });
    await waitFor(() => expect(screen.queryByTestId("review.modal")).not.toBeInTheDocument());
    // the score badge lights up from the server view
    expect(await screen.findByTestId("dial.score-badge")).toHaveTextContent("4");
  });

  it("dismiss hides the modal until the next block closes", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("review.modal");

    await user.click(screen.getByTestId("review.dismiss"));
    expect(screen.queryByTestId("review.modal")).not.toBeInTheDocument();

    // a new phase_changed does NOT reopen it (same pending segment)
    FakeSource.instances[0].emit("phase_changed", {
      phase: "work",
      segment_id: "s-1-2",
      ends_at: "2026-09-06T09:22:00+00:00",
      remaining_sec: 600,
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("review.modal")).not.toBeInTheDocument();
  });

  it("shows the day summary panel with server numbers", async () => {
    renderScreen();

    const panel = await screen.findByTestId("summary.panel");
    expect(panel).toHaveTextContent("Сводка дня");
    expect(screen.getByTestId("summary.stat-blocks")).toHaveTextContent("1 / 2");
    expect(screen.getByTestId("summary.stat-focus")).toHaveTextContent("10 мин");
  });
});
