/**
 * Vitest floor for pure option builders (spec 04 §5): data in, options out.
 * Geometry/formatting only — no DOM, no echarts instance (dial precedent).
 */

import { describe, expect, it } from "vitest";

import type { ChartLabels, HeatmapCellDto } from "@/api/types_stats";

import {
  estimateVsFactOption,
  goalDepthOption,
  heatmapOption,
  HEATMAP_LEVELS,
  quadrantsOption,
} from "./chartOptions";
import type { ChartTheme } from "./theme";

const THEME: ChartTheme = {
  text: "#111",
  muted: "#666",
  border: "#ddd",
  card: "#fff",
  work: "#e11d48",
  break: "#0d9488",
  accent: "#6366f1",
};

const LABELS: ChartLabels = {
  blocks: "блоки",
  minutes: "мин",
  estimate: "оценка",
  actual: "факт",
  tasks: "задач",
  doneRatio: "закрыто",
  weekdays: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
  months: ["янв", "фев"],
};

const CELLS: HeatmapCellDto[] = [
  { date: "2026-09-06", blocks_done: 9, focus_min: 108 },
  { date: "2026-09-07", blocks_done: 2, focus_min: 20 },
];

describe("heatmapOption", () => {
  it("maps cells to UTC-midnight [timestamp, blocks] pairs", () => {
    const option = heatmapOption(
      CELLS,
      { from: "2026-09-01", to: "2026-09-30" },
      THEME,
      LABELS
    );
    const data = option.series[0].data as unknown as { value: [number, number] }[];

    expect(data[0].value).toEqual([Date.parse("2026-09-06T00:00:00Z"), 9]);
    expect(data[1].value).toEqual([Date.parse("2026-09-07T00:00:00Z"), 2]);
  });

  it("keeps the calendar range pinned to the period", () => {
    const option = heatmapOption(
      CELLS,
      { from: "2026-09-01", to: "2026-09-30" },
      THEME,
      LABELS
    );

    expect(option.calendar.range).toEqual([
      Date.parse("2026-09-01T00:00:00Z"),
      Date.parse("2026-09-30T00:00:00Z"),
    ]);
  });

  it("renders piecewise levels from the spec thresholds", () => {
    const option = heatmapOption(CELLS, { from: "2026-09-01", to: "2026-09-30" }, THEME, LABELS);

    const pieces = option.visualMap.pieces as { min?: number; max?: number }[];
    // Levels 0 / 1-2 / 3-5 / 6-8 / 9+ (spec 04 §3): lower bounds in order.
    expect(pieces.slice(1).map((piece) => piece.min)).toEqual([...HEATMAP_LEVELS]);
    expect(pieces[0].max).toBe(0);
  });

  it("formats tooltip with blocks and minutes labels", () => {
    const option = heatmapOption(CELLS, { from: "2026-09-01", to: "2026-09-30" }, THEME, LABELS);
    const formatter = option.tooltip.formatter as (params: unknown) => string;

    const text = formatter({ value: [Date.parse("2026-09-06T00:00:00Z"), 9], data: { focus_min: 108 } });

    expect(text).toBe("2026-09-06 · 9 блоки · 108 мин");
  });
});

describe("estimateVsFactOption", () => {
  it("emits paired series and per-point categories", () => {
    const option = estimateVsFactOption(
      {
        ratio: 1.5,
        points: [
          { task_id: "t-1", title: "Alpha", estimate: 2, actual: 3 },
          { task_id: "t-2", title: "Beta", estimate: 1, actual: 1 },
        ],
      },
      THEME,
      LABELS
    );

    expect(option.xAxis.data).toEqual(["Alpha", "Beta"]);
    expect(option.series[0].data).toEqual([2, 1]);
    expect(option.series[1].data).toEqual([3, 1]);
    expect(option.series[0].name).toBe("оценка");
    expect(option.series[1].name).toBe("факт");
  });

  it("rotates dense category labels", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      task_id: `t-${i}`,
      title: `T${i}`,
      estimate: 1,
      actual: 1,
    }));

    const option = estimateVsFactOption({ ratio: 1, points: many }, THEME, LABELS);

    expect(option.xAxis.axisLabel.rotate).toBe(35);
  });
});

describe("quadrantsOption", () => {
  it("orders rows as given and colors the frog quadrant differently", () => {
    const rows = [
      { key: "important_urgent" as const, tasks_done: 2, blocks: 5, average_score: 4 },
      { key: "important_not_urgent" as const, tasks_done: 1, blocks: 3, average_score: 5 },
      { key: "urgent_not_important" as const, tasks_done: 0, blocks: 0, average_score: null },
      { key: "neither" as const, tasks_done: 4, blocks: 8, average_score: 2 },
    ];
    const names = ["Важно и срочно", "Важно · не срочно", "Срочно · не важно", "Пустота"];

    const option = quadrantsOption(rows, THEME, names);

    expect(option.yAxis.data).toEqual(names);
    expect(option.series[0].data.map((d: { value: number }) => d.value)).toEqual([5, 3, 0, 8]);
    const colors = option.series[0].data.map((d: { itemStyle: { color: string } }) => d.itemStyle.color);
    expect(new Set(colors)).toEqual(new Set([THEME.work, THEME.break]));
  });
});

describe("goalDepthOption", () => {
  it("uses filled_fields buckets as x and brightens done ratio", () => {
    const option = goalDepthOption(
      [
        { filled_fields: 0, tasks: 5, done_ratio: 0.2 },
        { filled_fields: 1, tasks: 2, done_ratio: 1.0 },
        { filled_fields: 2, tasks: 1, done_ratio: 0.0 },
        { filled_fields: 3, tasks: 4, done_ratio: 0.5 },
      ],
      THEME
    );

    expect(option.xAxis.data).toEqual(["0", "1", "2", "3"]);
    expect(option.series[0].data.map((d: { value: number }) => d.value)).toEqual([5, 2, 1, 4]);
    const opacities = option.series[0].data.map(
      (d: { itemStyle: { opacity: number } }) => d.itemStyle.opacity
    );
    expect(opacities[1]).toBeGreaterThan(opacities[0]);
    expect(opacities[2]).toBeLessThan(opacities[0]);
  });
});
