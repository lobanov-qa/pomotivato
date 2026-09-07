/**
 * Pure ECharts option builders for the dashboard (spec 04 §5).
 *
 * Tested by Vitest on data-in/options-out, no DOM (dial geometry precedent).
 * Colors come from ChartTheme (read from CSS vars by the screen), so the
 * builders stay deterministic; labels are injected (dictionary owns copy).
 */

import type {
  ChartLabels,
  EstimateVsFactDto,
  GoalDepthRowDto,
  HeatmapCellDto,
  QuadrantRowDto,
} from "@/api/types_stats";

import type { ChartTheme } from "./theme";

/** Heatmap levels per spec 04 §3: 0 / 1-2 / 3-5 / 6-8 / 9+ blocks. */
export const HEATMAP_LEVELS = [1, 3, 6, 9] as const;

function baseText(theme: ChartTheme) {
  return { color: theme.text, textStyle: { color: theme.text } };
}

function axisLabel(theme: ChartTheme) {
  return { color: theme.muted };
}

/** Calendar heatmap: [UTC-midnight-timestamp, blocks_done] cells only. */
export function heatmapOption(
  cells: HeatmapCellDto[],
  period: { from: string; to: string },
  theme: ChartTheme,
  labels: ChartLabels
) {
  const start = Date.parse(`${period.from}T00:00:00Z`);
  const end = Date.parse(`${period.to}T00:00:00Z`);
  const data = cells.map((cell) => ({
    value: [Date.parse(`${cell.date}T00:00:00Z`), cell.blocks_done],
    focus_min: cell.focus_min,
  }));
  return {
    ...baseText(theme),
    tooltip: {
      formatter: (params: { value: [number, number]; data: { focus_min: number } }) => {
        const day = new Date(params.value[0]).toISOString().slice(0, 10);
        return `${day} · ${params.value[1]} ${labels.blocks} · ${params.data.focus_min} ${labels.minutes}`;
      },
    },
    visualMap: {
      min: 0,
      max: 9,
      type: "piecewise",
      pieces: [
        { max: 0, color: theme.border },
        { min: 1, max: 2, color: theme.work, opacity: 0.35 },
        { min: 3, max: 5, color: theme.work, opacity: 0.55 },
        { min: 6, max: 8, color: theme.work, opacity: 0.8 },
        { min: 9, color: theme.work },
      ],
      show: false,
    },
    calendar: {
      range: [start, end],
      cellSize: [14, 14],
      left: 30,
      top: 12,
      itemStyle: { color: theme.card, borderColor: theme.border, borderWidth: 1 },
      yearLabel: { show: false },
      monthLabel: { color: theme.muted },
      dayLabel: { nameMap: labels.weekdays, color: theme.muted, firstDay: 1 },
      splitLine: { show: false },
    },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data }],
  };
}

/** Paired bars estimate vs fact per DONE task (spec 04 §3). */
export function estimateVsFactOption(
  data: EstimateVsFactDto,
  theme: ChartTheme,
  labels: ChartLabels
) {
  const titles = data.points.map((point) => point.title);
  return {
    ...baseText(theme),
    legend: { textStyle: axisLabel(theme), top: 0 },
    grid: { left: 36, right: 12, top: 32, bottom: 48 },
    xAxis: {
      type: "category",
      data: titles,
      axisLabel: { ...axisLabel(theme), rotate: titles.length > 6 ? 35 : 0, hideOverlap: true },
      axisLine: { lineStyle: { color: theme.border } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: axisLabel(theme),
      splitLine: { lineStyle: { color: theme.border } },
    },
    series: [
      {
        name: labels.estimate,
        type: "bar",
        data: data.points.map((point) => point.estimate),
        itemStyle: { color: theme.muted },
      },
      {
        name: labels.actual,
        type: "bar",
        data: data.points.map((point) => point.actual),
        itemStyle: { color: theme.work },
      },
    ],
  };
}

/** Quadrant retro: completed blocks per Eisenhower cell (spec 04 §3).
 * names[i] pairs with rows[i] — RU labels are injected by the screen (the
 * dictionary owns copy), keys stay the wire contract. */
export function quadrantsOption(rows: QuadrantRowDto[], theme: ChartTheme, names: string[]) {
  return {
    ...baseText(theme),
    grid: { left: 12, right: 24, top: 16, bottom: 12, containLabel: true },
    xAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: axisLabel(theme),
      splitLine: { lineStyle: { color: theme.border } },
    },
    yAxis: {
      type: "category",
      data: names,
      axisLabel: { ...axisLabel(theme), fontSize: 10 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: theme.border } },
    },
    series: [
      {
        type: "bar",
        data: rows.map((row) => ({
          value: row.blocks,
          itemStyle: { color: row.key === "important_not_urgent" ? theme.break : theme.work },
        })),
      },
    ],
  };
}

/** Goal depth: tasks per scientific-fields bucket; opacity = done ratio. */
export function goalDepthOption(rows: GoalDepthRowDto[], theme: ChartTheme) {
  return {
    ...baseText(theme),
    grid: { left: 36, right: 12, top: 16, bottom: 24 },
    xAxis: {
      type: "category",
      data: rows.map((row) => String(row.filled_fields)),
      axisLabel: axisLabel(theme),
      axisLine: { lineStyle: { color: theme.border } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: axisLabel(theme),
      splitLine: { lineStyle: { color: theme.border } },
    },
    series: [
      {
        type: "bar",
        data: rows.map((row) => ({
          value: row.tasks,
          itemStyle: { color: theme.work, opacity: 0.35 + 0.65 * row.done_ratio },
        })),
      },
    ],
  };
}
