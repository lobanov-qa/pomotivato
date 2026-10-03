import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TaskDto } from "@/api/client";
import { KanbanScreen } from "./KanbanScreen";

/**
 * Screen level (render + data flow): fetch is stubbed at the transport so
 * the real client/hook/mutation wiring is exercised. Drag physics is
 * dnd-kit's own tested code; our rules around it live in board.test.ts.
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Write tests",
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
    sprint_id: null,
    carry_choice: null,
    done_at: null,
    blocks_done: null,
    days_done: null,
    last_worked: null,
    days_missed: null,
    days_left: null,
    closeable: null,
    created_at: `${new Date().toLocaleDateString("en-CA")}T09:00:00+00:00`,
    ...overrides,
  };
}

let frogId: string | null = null;

const BOARD: TaskDto[] = [
  task({ id: "a", title: "Backlog card" }),
  task({ id: "b", title: "Planned card", status: "planned", estimate_blocks: 2 }),
  task({ id: "c", title: "Doing card", status: "doing", estimate_blocks: 2, when_then: "если 9:00 → пишу" }),
  task({ id: "d", title: "Done card", status: "done" }),
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  frogId = null;
  SPRINTS = [];
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/tasks")) {
      return jsonResponse(200, BOARD);
    }
    if (url.startsWith("/api/day-plans/")) {
      return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
    }
    if (url === "/api/frog") {
      return jsonResponse(200, { task_id: frogId });
    }
    if (url === "/api/settings") {
      return jsonResponse(200, SETTINGS_ON);
    }
    if (url === "/api/sprints") {
      return jsonResponse(200, SPRINTS);
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

let SPRINTS: unknown[] = [];

const SETTINGS_ON = {
  session: {
    work_min: 25,
    break_min: 5,
    long_break_min: 15,
    long_break_every: 4,
    auto_start_next: true,
  },
  ui: {
    max_in_work: 6,
    theme: "auto",
    require_science_fields: false,
    wet_hints: true,
    done_visible_limit: 10,
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <KanbanScreen />
    </QueryClientProvider>,
  );
}

describe("KanbanScreen", () => {
  it("renders four RU columns with cards grouped by status", async () => {
    renderScreen();

    await screen.findByTestId("task-card.root-a"); // data arrived
    expect(screen.getByTestId("kanban.column-backlog")).toHaveTextContent("Backlog card");
    expect(screen.getByTestId("kanban.column-planned")).toHaveTextContent("Planned card");
    expect(screen.getByTestId("kanban.column-doing")).toHaveTextContent("Doing card");
    expect(screen.getByTestId("kanban.column-done")).toHaveTextContent("Done card");
    // no archived lane leaks cards onto the board
    expect(screen.queryByText(/Archived/)).not.toBeInTheDocument();
  });

  it("shows card meta line on the face (type/quadrant/blocks)", async () => {
    renderScreen();

    await screen.findByTestId("task-card.root-b");
    expect(screen.getByTestId("task-card.type-b")).toHaveTextContent("Обычная");
    expect(screen.getByTestId("task-card.quadrant-b")).toHaveTextContent(
      "Не важно · не срочно",
    );
    expect(screen.getByTestId("task-card.blocks-b")).toHaveTextContent("2");
  });

  it("derives the day plan from the doing column (today = the dial)", async () => {
    renderScreen();

    const first = await screen.findByTestId("planner.slot-1");
    expect(first).toHaveTextContent("Doing card");
    expect(screen.getByTestId("planner.slot-2")).toHaveTextContent("Doing card");
    expect(screen.queryByTestId("planner.slot-3")).not.toBeInTheDocument();
  });

  it("refuses a blocked delete and explains it in RU (DF1)", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/tasks/a" && init?.method === "DELETE") {
        return jsonResponse(409, {
          detail: { code: "conflict", message: "task 'a' is planned on ['2026-09-10']" },
        });
      }
      if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-a"));
    await user.click(await screen.findByTestId("task-panel.delete-a"));

    expect(await screen.findByTestId("kanban.conflict-toast")).toHaveTextContent("стоит в плане");
  });

  it("duplicates a done card via POST clone (DF12)", async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://x");
      if (url.pathname === "/api/tasks/d/clone" && init?.method === "POST") {
        posts.push(url.pathname);
        return jsonResponse(201, task({ id: "clone-x", status: "backlog", cloned_from: "d" }));
      }
      if (url.pathname === "/api/tasks") return jsonResponse(200, BOARD);
      if (url.pathname.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url.pathname === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url.pathname === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-d"));
    await user.click(await screen.findByTestId("task-panel.clone-d"));

    expect(posts).toEqual(["/api/tasks/d/clone"]);
  });

  it("creates a task from the quick-add form via POST", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/tasks" && init?.method === "POST") {
          return jsonResponse(201, task({ id: "new-1", title: "Fresh card" }));
        }
        if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
        if (url.startsWith("/api/settings")) {
          return jsonResponse(200, {
            session: {
              work_min: 25,
              break_min: 5,
              long_break_min: 15,
              long_break_every: 4,
              auto_start_next: true,
            },
            ui: { max_in_work: 12, theme: "auto" },
          });
        }
        if (url === "/api/sprints") return jsonResponse(200, []);
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      },
    );
    renderScreen();
    await screen.findByTestId("kanban.column-backlog");

    await user.type(screen.getByTestId("kanban.create-input"), "Fresh card");
    await user.click(screen.getByTestId("kanban.create-submit"));

    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([url, init]) => url === "/api/tasks" && (init as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.title).toBe("Fresh card");
      expect(body.id).toMatch(/^task-/);
    });
  });

  it("ticks sprint days via the panel and PATCHes on_dates (DF8)", async () => {
    const user = userEvent.setup();
    // Stateful mock: PATCH mutates the live list and GET returns it — the
    // second tick must build on the card the server already saved.
    // The sprint's tick row belongs to the CARD's own container now
    // (E4c §4.5), so card "a" lives in the band sprint for this case.
    const live = BOARD.map((t) => (t.id === "a" ? { ...t, sprint_id: "s-1" } : { ...t }));
    // E4c PR 4: the row gained the V21 guard (past days are not tickable),
    // so the band must cover the real today — window anchored to now.
    const now = new Date().toLocaleDateString("en-CA");
    const dayAfter = new Date(Date.now() + 86_400_000).toLocaleDateString("en-CA");
    const dayAhead = new Date(Date.now() + 2 * 86_400_000).toLocaleDateString("en-CA");
    const sprint = {
      id: "s-1",
      number: 1,
      name: "w37",
      goal: null,
      done_criteria: null,
      start_date: now,
      end_date: dayAhead,
      status: "active",
    };
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();
      if (url === "/api/tasks" && method === "GET") return jsonResponse(200, live);
      const patchMatch = /^\/api\/tasks\/([\w-]+)$/.exec(url);
      if (patchMatch && method === "PATCH") {
        const card = live.find((t) => t.id === patchMatch[1]);
        if (!card) return jsonResponse(404, { detail: "gone" });
        Object.assign(card, JSON.parse(String(init?.body)));
        return jsonResponse(200, card);
      }
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, [sprint]);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-a"));
    await user.click(await screen.findByTestId(`task-panel.day-a-${now}`));
    await waitFor(() =>
      expect(screen.getByTestId(`task-panel.day-a-${now}`)).toHaveAttribute("aria-pressed", "true"),
    );
    await user.click(screen.getByTestId(`task-panel.day-a-${dayAfter}`));

    await waitFor(() => {
      const patches = fetchMock.mock.calls
        .filter(
          ([url, init]) => url === "/api/tasks/a" && (init as RequestInit)?.method === "PATCH",
        )
        .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
      expect(patches.at(-1)?.recurrence).toEqual({ kind: "on_dates", days: [now, dayAfter] });
    });
  });

  it("panel shows the §4.7 state line and close-card POSTs /close (E4c PR 4)", async () => {
    const user = userEvent.setup();
    const now = new Date().toLocaleDateString("en-CA");
    const yesterday = new Date(Date.now() - 86_400_000).toLocaleDateString("en-CA");
    const live: TaskDto[] = [
      task({
        id: "m",
        title: "Missed hole",
        recurrence: { kind: "on_dates", days: [yesterday, now] },
        days_missed: [yesterday],
      }),
    ];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = String(init?.method ?? "GET").toUpperCase();
      if (url === "/api/tasks" && method === "GET") return jsonResponse(200, live);
      if (url === "/api/tasks/m" && method === "PATCH") {
        Object.assign(live[0], JSON.parse(String(init?.body)) as object);
        return jsonResponse(200, live[0]);
      }
      if (url === "/api/tasks/m/close" && method === "POST") {
        // the V31 refusal travels as 409 (a missed tick still blocks)
        return jsonResponse(409, { detail: { code: "conflict", message: "missed day" } });
      }
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: now, slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: null });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("task-card.edit-m"));
    const state = await screen.findByTestId("task-panel.state-m");
    // dd.MM of the missed day is named, and the block explanation is there.
    expect(state.textContent).toContain(`${yesterday.slice(8)}.${yesterday.slice(5, 7)}`);
    expect(state.textContent).toContain("Пропущен день");
    // V32 close is not offered while a hole remains.
    expect(screen.queryByTestId("task-panel.close-card-m")).not.toBeInTheDocument();

    // Server-side the author works the day: the hole closes, the card becomes
    // closeable. A title PATCH drives invalidateBoard -> a fresh GET (the
    // TanStack cache never refetches on its own, lesson #46) and the panel
    // re-renders from the new DTO.
    Object.assign(live[0], {
      days_missed: [],
      days_left: [],
      closeable: true,
      recurrence: { kind: "on_dates", days: [yesterday] },
      days_done: 1,
    });
    await user.clear(screen.getByTestId("task-panel.title-m"));
    await user.type(screen.getByTestId("task-panel.title-m"), "Hole healed");

    const button = await screen.findByTestId("task-panel.close-card-m");
    await user.click(button);

    await waitFor(() =>
      expect(screen.getByTestId("kanban.conflict-toast")).toHaveTextContent("Закрыть нельзя"),
    );
    const closed = fetchMock.mock.calls.some(
      ([url, init]) => url === "/api/tasks/m/close" && (init as RequestInit)?.method === "POST",
    );
    expect(closed).toBe(true);
  });

  it("board reads one scope: sprint card by default, shelf after the switch (E4c selector)", async () => {
    const user = userEvent.setup();
    const scoped = {
      ...task({ id: "s1", title: "Sprint card" }),
      status: "backlog" as const,
      sprint_id: "sp-1",
    };
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/tasks")) return jsonResponse(200, [...BOARD, scoped]);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") {
        return jsonResponse(200, [
          {
            id: "sp-1",
            number: 3,
            name: "w39",
            start_date: new Date().toLocaleDateString("en-CA"),
            end_date: new Date(Date.now() + 86_400_000).toLocaleDateString("en-CA"),
            goal: null,
            done_criteria: null,
            status: "active",
            unfinished_count: 0,
            carry_pending: 0,
            is_current: true,
          },
        ]);
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    // default scope: the sprint covering today wins over the shelf (spec 4.3)
    expect(await screen.findByTestId("task-card.root-s1")).toBeInTheDocument();
    expect(screen.queryByTestId("task-card.root-a")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByTestId("kanban.scope-select"), "none");

    // the shelf appears; the choice rides the URL (?sprint=none)
    await screen.findByTestId("task-card.root-a");
    expect(screen.getByTestId("task-card.root-a")).toBeInTheDocument();
    expect(screen.queryByTestId("task-card.root-s1")).not.toBeInTheDocument();
    expect(window.location.search).toContain("sprint=none");

    // quick-add lands in the selected scope (V28/A13)
    await user.type(screen.getByTestId("kanban.create-input"), "Shelf fresh");
    await user.click(screen.getByTestId("kanban.create-submit"));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([url, init]) => url === "/api/tasks" && (init as RequestInit)?.method === "POST",
      );
      expect(post).toBeTruthy();
      const body = JSON.parse(String((post![1] as RequestInit).body));
      expect(body.sprint_id).toBeNull(); // the shelf
    });
  });

  it("shows the done/total dot row for a ticked card (DF10)", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/tasks")) {
        return jsonResponse(
          200,
          [
            {
              ...task({ id: "r" }),
              recurrence: {
                kind: "on_dates",
                days: ["2026-09-09", "2026-09-10", "2026-09-11"],
              },
              blocks_done: 5, // blocks do not fill the dots any more
              days_done: 2,
            },
          ],
        );
      }
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: null });
      if (url === "/api/settings") return jsonResponse(200, SETTINGS_ON);
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    const dots = await screen.findByTestId("task-card.progress-r");
    expect(dots).toHaveTextContent("2/3");
    expect(dots).toHaveAccessibleName("Прогресс: 2 из 3");
  });

  it("arrows reorder the dial plan as whole blocks (DF4-lite)", async () => {
    const user = userEvent.setup();
    const doing = [
      task({ id: "c", title: "Doing card", status: "doing", estimate_blocks: 2 }),
      task({ id: "x", title: "Second doing", status: "doing", estimate_blocks: 1 }),
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.startsWith("/api/day-plans/") && init?.method === "PUT") {
          return jsonResponse(200, JSON.parse(String(init.body)) as { id: string });
        }
        if (url.startsWith("/api/tasks")) return jsonResponse(200, doing);
        if (url.startsWith("/api/day-plans/"))
          return jsonResponse(200, { id: "p", date: "2026-09-08", slots: [] });
        if (url === "/api/frog") return jsonResponse(200, { task_id: null, reason: null });
        if (url === "/api/settings/ui") return jsonResponse(200, { ui: { theme: "auto" } });
        if (url === "/api/sprints") return jsonResponse(200, []);
        return jsonResponse(404, { error: { code: "not_found", message: url } });
      }),
    );
    render(<QueryClientProvider client={new QueryClient()}><KanbanScreen /></QueryClientProvider>);
    // column order c(2 blocks) + x(1): sectors c,c,x — row shows both.
    const order = await screen.findByTestId("kanban.planner-order");
    expect(within(order).getByTestId("planner.order-c")).toBeTruthy();
    await user.click(within(order).getByTestId("planner.order-up-x"));
    await waitFor(() => {
      const put = (fetch as ReturnType<typeof vi.fn>).mock.calls
        .map(([url, init]) => ({ url: String(url), init: init as RequestInit | undefined }))
        .find((call) => call.url.startsWith("/api/day-plans/") && call.init?.method === "PUT");
      expect(put).toBeTruthy();
      const body = JSON.parse(String(put?.init?.body)) as { slots: { task_id: string }[] };
      // the whole x block jumped over the whole c block: x,c,c
      expect(body.slots.map((s) => s.task_id)).toEqual(["x", "c", "c"]);
    });
  });

  it("opens the side panel for ONE card (DF2 replaces column-wide edit)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    await user.click(screen.getByTestId("task-card.edit-a"));

    const panel = await screen.findByTestId("task-panel.root-a");
    expect(panel).toBeInTheDocument();
    expect(screen.getByTestId("task-panel.title-a")).toHaveValue("Backlog card");
    expect(screen.getByTestId("task-panel.quadrant-a")).toBeInTheDocument();
    // the other card never gets a form: editing is per-card now
    expect(screen.queryByTestId("task-panel.root-c")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("task-panel.close"));
    expect(screen.queryByTestId("task-panel.root-a")).not.toBeInTheDocument();
  });

  it("Esc closes the card panel (U2 overlay law)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    await user.click(screen.getByTestId("task-card.edit-a"));
    await screen.findByTestId("task-panel.root-a");
    await user.keyboard("{Escape}");

    expect(screen.queryByTestId("task-panel.root-a")).not.toBeInTheDocument();
  });

  it("the done column carries the V26 trim hint with the live limit", async () => {
    renderScreen();
    await screen.findByTestId("kanban.screen");

    // §4.6: the hover note names the limit and the archive; only «Готово» has one
    expect(screen.getByTestId("kanban.column-title-done")).toHaveAttribute(
      "title",
      expect.stringContaining("сверх лимита (10)"),
    );
    expect(screen.getByTestId("kanban.column-title-backlog")).not.toHaveAttribute("title");
  });

  it("wet-hint marks only scheduled cards with a blank when_then", async () => {
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.wt-hint-b")).toBeInTheDocument(); // planned, blank
    expect(screen.queryByTestId("task-card.wt-hint-c")).not.toBeInTheDocument(); // has when_then
    expect(screen.queryByTestId("task-card.wt-hint-a")).not.toBeInTheDocument(); // backlog: no ring
    expect(screen.queryByTestId("task-card.wt-hint-d")).not.toBeInTheDocument(); // done: no ring
  });

  it("wet-hint rings switch off when the server says so (DF6)", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/settings") {
        return jsonResponse(200, {
          ...SETTINGS_ON,
          ui: { ...SETTINGS_ON.ui, wet_hints: false },
        });
      }
      if (url.startsWith("/api/tasks")) return jsonResponse(200, BOARD);
      if (url.startsWith("/api/day-plans/")) {
        return jsonResponse(200, { id: "p", date: "2026-09-05", slots: [] });
      }
      if (url === "/api/frog") return jsonResponse(200, { task_id: frogId });
      if (url === "/api/sprints") return jsonResponse(200, []);
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.queryByTestId("task-card.wt-hint-b")).not.toBeInTheDocument();
  });

  it("frog badge lights the server-computed candidate", async () => {
    frogId = "b";
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.frog-badge-b")).toBeInTheDocument();
    expect(screen.queryByTestId("task-card.frog-badge-a")).not.toBeInTheDocument();
    frogId = null;
  });

  it("wet-hint stays on the card face while its panel is open (DF2)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.wt-hint-b");

    await user.click(screen.getByTestId("task-card.edit-b"));

    expect(screen.getByTestId("task-card.wt-hint-b")).toBeInTheDocument();
    expect(screen.getByTestId("task-panel.root-b")).toBeInTheDocument();
  });
});
