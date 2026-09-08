/**
 * Sprint band -> modal flow (spec 05 §3.10 / ⚑ Q8): the create form posts
 * name/goal/period, period presets clamp to 1/2 weeks, and 14-day V14 is
 * guarded client-side before the POST.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SprintBand } from "@/components/week/SprintBand";

const monday = "2026-09-07";
const post: { url: string; body: unknown }[] = [];

beforeEach(() => {
  post.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://x");
      if (url.pathname === "/api/sprints" && (!init?.method || init.method === "GET")) {
        return new Response("[]", { headers: { "content-type": "application/json" } });
      }
      if (url.pathname === "/api/sprints" && init?.method === "POST") {
        post.push({ url: url.pathname, body: JSON.parse(String(init.body)) });
        return new Response(
          JSON.stringify({ id: "s-1", number: 1, status: "planned", ...JSON.parse(String(init.body)) }),
          { status: 201, headers: { "content-type": "application/json" } },
        );
      }
      return new Response("[]", { status: 200 });
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderBand() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SprintBand windowDates={[monday, "2026-09-08", "2026-09-09"]} />
    </QueryClientProvider>
  );
}

describe("SprintBand", () => {
  it("create -> modal prefilled with the window Monday -> POST lands", async () => {
    renderBand();

    await userEvent.click(await screen.findByTestId("week.sprint-create"));
    await userEvent.type(screen.getByTestId("sprint.form-name"), "w37");
    await userEvent.click(screen.getByTestId("sprint.preset-7"));
    await userEvent.click(screen.getByTestId("sprint.save"));

    await waitFor(() => expect(post).toHaveLength(1));
    expect(post[0].body).toMatchObject({
      name: "w37",
      start_date: monday,
      end_date: "2026-09-13", // 7-day period inclusive
    });
    await waitFor(() => expect(screen.queryByTestId("sprint.modal")).not.toBeInTheDocument());
  });

  it("period longer than 14 days blocks the save button (V14 mirror)", async () => {
    renderBand();

    await userEvent.click(await screen.findByTestId("week.sprint-create"));
    const end = screen.getByTestId("sprint.form-end");
    await userEvent.clear(end);
    await userEvent.type(end, "2026-10-05");

    expect(screen.getByTestId("sprint.form-error")).toBeInTheDocument();
    expect(screen.getByTestId("sprint.save")).toBeDisabled();
  });
});
