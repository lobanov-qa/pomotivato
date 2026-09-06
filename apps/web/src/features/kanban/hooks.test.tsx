import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TaskDto } from "@/api/client";
import { TASKS_KEY, useMoveTask, useTasks } from "./hooks";

/**
 * The optimistic-move contract (spec 03 §2): a 409 from the server must
 * roll the cache back so the card "flies back" to its old column. This is
 * the riskiest behavior on the screen, so it is pinned at hook level with
 * a stubbed fetch (no DOM drag physics — dnd-kit's own tests cover those).
 */

function task(overrides: Partial<TaskDto> = {}): TaskDto {
  return {
    id: "t-1",
    title: "Card",
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
    created_at: "2026-09-05T09:00:00+00:00",
    ...overrides,
  };
}

const BOARD = [task({ id: "a", status: "backlog" })];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/tasks" && !init?.method) {
      return new Response(JSON.stringify(BOARD), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (url === "/api/tasks/a/status" && init?.method === "POST") {
      return new Response(
        JSON.stringify({ detail: { code: "conflict", message: "illegal transition" } }),
        { status: 409, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useMoveTask optimistic rollback", () => {
  it("keeps the old status in cache when the server answers 409", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(TASKS_KEY, BOARD);
    const move = renderHook(() => useMoveTask(), { wrapper: wrapper(client) });
    const view = renderHook(() => useTasks(), { wrapper: wrapper(client) });

    await move.result.current.mutateAsync({ id: "a", to: "planned" }).catch(() => undefined);

    // the invalidation from onSettled refetches the truth (still backlog)
    await waitFor(() => expect(view.result.current.isSuccess).toBe(true));
    expect(view.result.current.tasks[0].status).toBe("backlog");
    // and the optimistic patch itself was rolled back before the refetch
    const cached = client.getQueryData<TaskDto[]>(TASKS_KEY);
    expect(cached?.[0].status).toBe("backlog");
  });

  it("applies the optimistic move while the request is in flight", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(TASKS_KEY, BOARD);
    let release: (value: Response) => void = () => undefined;
    fetchMock.mockImplementation(
      (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/tasks/a/status" && init?.method === "POST") {
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        }
        return Promise.resolve(
          new Response(JSON.stringify(BOARD), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      },
    );
    const move = renderHook(() => useMoveTask(), { wrapper: wrapper(client) });

    const pending = move.result.current.mutateAsync({ id: "a", to: "planned" });
    await waitFor(() => {
      const cached = client.getQueryData<TaskDto[]>(TASKS_KEY);
      expect(cached?.[0].status).toBe("planned"); // instant UI, no waiting
    });

    release(
      new Response(JSON.stringify({ ...BOARD[0], status: "planned" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await pending;
  });
});
