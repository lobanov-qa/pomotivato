/**
 * Vitest smoke for the thin Chart host + theme reader. echarts is mocked:
 * jsdom has no canvas, and we only pin ownership (init/dispose/setOption),
 * not library internals. matchMedia/ResizeObserver come from test/setup.ts.
 */

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Chart } from "./Chart";
import { chartThemeFrom } from "./theme";

const initMock = vi.fn();
const setOptionMock = vi.fn();
const disposeMock = vi.fn();

vi.mock("echarts", () => ({
  init: (...args: unknown[]) => {
    initMock(...args);
    return {
      setOption: setOptionMock,
      dispose: disposeMock,
      resize: vi.fn(),
    };
  },
}));

beforeEach(() => {
  initMock.mockClear();
  setOptionMock.mockClear();
  disposeMock.mockClear();
});

describe("Chart", () => {
  it("mounts one host div with the registry testid", () => {
    render(<Chart option={{}} testId="stats.widget-heatmap" />);

    expect(screen.getByTestId("stats.widget-heatmap")).toBeInTheDocument();
    expect(initMock).toHaveBeenCalledTimes(1);
  });

  it("applies the option with notMerge after mount", () => {
    const option = { series: [] };

    render(<Chart option={option} testId="stats.widget-estimate" />);

    expect(setOptionMock).toHaveBeenCalledWith(option, true);
  });

  it("disposes the instance on unmount", () => {
    const view = render(<Chart option={{}} testId="stats.widget-quadrants" />);

    view.unmount();

    expect(disposeMock).toHaveBeenCalledTimes(1);
  });
});

describe("chartThemeFrom", () => {
  it("reads the live CSS custom properties", () => {
    document.documentElement.style.setProperty("--color-work", "#123456");

    const theme = chartThemeFrom();

    expect(theme.work).toBe("#123456");
    document.documentElement.style.removeProperty("--color-work");
  });

  it("falls back when a variable is absent", () => {
    const theme = chartThemeFrom(null);

    expect(theme.work).toBeTruthy();
  });
});
