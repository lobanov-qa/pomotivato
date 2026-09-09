import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
    created_at: "2026-09-05T09:00:00+00:00",
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
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

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

  it("shows card meta line when not editing (type/quadrant/blocks)", async () => {
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
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("kanban.edit-toggle-backlog"));
    await user.click(await screen.findByTestId("task-card.delete-a"));

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
      throw new Error(`unexpected fetch: ${url}`);
    });
    renderScreen();

    await user.click(await screen.findByTestId("kanban.edit-toggle-done"));
    await user.click(await screen.findByTestId("task-card.clone-d"));

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

  it("column edit toggle swaps cards into the edit form", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.root-a");

    await user.click(screen.getByTestId("kanban.edit-toggle-backlog"));

    expect(screen.getByTestId("task-card.title-a")).toHaveValue("Backlog card");
    expect(screen.getByTestId("task-card.quadrant-a")).toBeInTheDocument();
    // drag grips switch off while the column is in edit mode (dnd-kit marks
    // the listener node aria-disabled; invisible is a Tailwind class jsdom
    // cannot compute)
    expect(screen.getByTestId("task-card.grip-a")).toHaveAttribute("aria-disabled", "true");
  });

  it("wet-hint marks only scheduled cards with a blank when_then", async () => {
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.wt-hint-b")).toBeInTheDocument(); // planned, blank
    expect(screen.queryByTestId("task-card.wt-hint-c")).not.toBeInTheDocument(); // has when_then
    expect(screen.queryByTestId("task-card.wt-hint-a")).not.toBeInTheDocument(); // backlog: no ring
    expect(screen.queryByTestId("task-card.wt-hint-d")).not.toBeInTheDocument(); // done: no ring
  });

  it("frog badge lights the server-computed candidate", async () => {
    frogId = "b";
    renderScreen();
    await screen.findByTestId("task-card.root-b");

    expect(screen.getByTestId("task-card.frog-badge-b")).toBeInTheDocument();
    expect(screen.queryByTestId("task-card.frog-badge-a")).not.toBeInTheDocument();
    frogId = null;
  });

  it("edit mode hides the science hint rows (forms own the fields)", async () => {
    const user = userEvent.setup();
    renderScreen();
    await screen.findByTestId("task-card.wt-hint-b");

    await user.click(screen.getByTestId("kanban.edit-toggle-planned"));

    expect(screen.queryByTestId("task-card.wt-hint-b")).not.toBeInTheDocument();
  });
});
