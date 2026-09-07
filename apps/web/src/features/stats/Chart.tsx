/**
 * Thin ECharts host (spec 04 §5): init/dispose, setOption on props change,
 * resize via ResizeObserver. No chart logic lives here — options are built
 * by pure chartOptions builders (Vitest-tested), colors by CSS variables.
 * Theme re-paint is driven by useThemeEpoch (./hooks), not by this file.
 */

import { useEffect, useRef } from "react";

import * as echarts from "echarts";

export interface ChartProps {
  option: echarts.EChartsOption;
  height?: number;
  /** Semantic testid from the private registry (plan/TESTIDS.md). */
  testId: string;
}

export function Chart({ option, height = 220, testId }: ChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = echarts.init(host);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge: a theme flip must fully replace old colors, not merge into.
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={hostRef} data-testid={testId} style={{ height, width: "100%" }} />;
}
