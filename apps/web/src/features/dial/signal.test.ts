import { describe, expect, it, vi } from "vitest";
import type { SignalKind } from "@/api/client";
import { TimerSignal, playSignal, type AudioContextLike } from "./signal";
import { formatTabTitle, mmss } from "./tabTitle";

/**
 * Timer signal and tab title (spec 07 §1 p.22, §10.10, §10.14; DF33 shape
 * picker, E4c-UX 5/5). §10.14 is law here: the title is asserted as a
 * FUNCTION, never as document.title (e2e owns the DOM later); the signal
 * is asserted against a fake AudioContext — scheduling on the audio clock
 * is the contract, the shapes are contracts too (start/stop windows).
 */

type Call = [string, number];

function fakeCtx(startAt = 10): AudioContextLike & { calls: Call[] } {
  const now = startAt;
  const calls: Call[] = [];
  return {
    calls,
    get currentTime() {
      return now;
    },
    destination: {},
    createOscillator: () => {
      const node = {
        type: "",
        frequency: {
          value: 0,
          setValueAtTime: vi.fn(),
          linearRampToValueAtTime: vi.fn(),
        },
        connect: vi.fn(),
        start: (when: number) => calls.push(["osc-start", when]),
        stop: (when: number) => calls.push(["osc-stop", when]),
      };
      return node;
    },
    createGain: () => ({
      connect: vi.fn(),
      gain: {
        value: 0,
        setValueAtTime: vi.fn(),
        linearRampToValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
    }),
  };
}

const startsOf = (ctx: AudioContextLike & { calls: Call[] }): number[] =>
  ctx.calls.filter((call) => call[0] === "osc-start").map((call) => call[1]);
const stopsOf = (ctx: AudioContextLike & { calls: Call[] }): number[] =>
  ctx.calls.filter((call) => call[0] === "osc-stop").map((call) => call[1]);

describe("playSignal (DF33 shapes on the audio clock)", () => {
  const KINDS: SignalKind[] = [
    "bell-trill",
    "siren",
    "pulse-alarm",
    "rising-tone",
    "chime-melody",
  ];

  it.each(KINDS)("every shape starts at `when` and ends within ~2 s: %s", (kind) => {
    const ctx = fakeCtx();

    const nodes = playSignal(kind, ctx, 40);

    expect(nodes.length).toBeGreaterThan(0);
    expect(startsOf(ctx)[0]).toBe(40);
    const lastStop = Math.max(...stopsOf(ctx));
    expect(lastStop).toBeLessThanOrEqual(42.1); // a two-second event, plus slack
  });

  it("bell-trill strikes three overlapping bells", () => {
    const ctx = fakeCtx();

    playSignal("bell-trill", ctx, 40);

    const starts = [...new Set(startsOf(ctx))].sort((a, b) => a - b);
    expect(starts).toEqual([40, 40.6, 41.2]);
  });

  it("pulse-alarm beeps nine short hits inside the window", () => {
    const ctx = fakeCtx();

    const nodes = playSignal("pulse-alarm", ctx, 40);

    expect(nodes).toHaveLength(9);
    expect(startsOf(ctx).length).toBe(9);
  });

  it("an unknown kind falls back to the default bell-trill", () => {
    const ctx = fakeCtx();

    playSignal("does-not-exist" as SignalKind, ctx, 40);

    expect(startsOf(ctx).length).toBeGreaterThan(0);
  });
});

describe("TimerSignal", () => {
  it("silence before attach: no gesture, no context, no chime (§10.10 p.1)", () => {
    const signal = new TimerSignal();
    const factory = vi.fn(() => fakeCtx());

    signal.schedule(600);

    expect(signal.attached).toBe(false);
    expect(factory).not.toHaveBeenCalled();
  });

  it("attach is idempotent: one context per session lifetime", () => {
    const signal = new TimerSignal();
    const factory = vi.fn(() => fakeCtx());

    signal.attach(factory);
    signal.attach(factory);

    expect(factory).toHaveBeenCalledTimes(1);
    expect(signal.attached).toBe(true);
  });

  it("schedule parks the chosen signal at currentTime + remaining", () => {
    const ctx = fakeCtx(10);
    const signal = new TimerSignal();
    signal.attach(() => ctx);

    signal.schedule(600, "pulse-alarm");

    expect(startsOf(ctx)[0]).toBe(610);
    expect(startsOf(ctx).length).toBe(9); // the pulse shape, parked
  });

  it("re-scheduling cancels the parked signal (a new phase, not two deadlines)", () => {
    const ctx = fakeCtx(0);
    const signal = new TimerSignal();
    signal.attach(() => ctx);

    signal.schedule(1200);
    signal.schedule(300);

    // the first batch got stop(0) calls before the second was parked
    const stops = ctx.calls.filter((call) => call[0] === "osc-stop");
    expect(stops).toContainEqual(["osc-stop", 0]);
    expect(stops[stops.length - 1]).not.toEqual(["osc-stop", 0]); // fresh signal scheduled on
  });

  it("cancel drops a parked signal without scheduling anything", () => {
    const ctx = fakeCtx(0);
    const signal = new TimerSignal();
    signal.attach(() => ctx);
    signal.schedule(900);
    ctx.calls.length = 0;

    signal.cancel();

    const stops = stopsOf(ctx);
    expect(stops.length).toBeGreaterThan(0);
    expect(stops.every((stop) => stop === 0)).toBe(true);
  });
});

describe("tab title (pure per §10.14)", () => {
  it("mmss floors to zero and pads", () => {
    expect(mmss(0)).toBe("00:00");
    expect(mmss(-5)).toBe("00:00");
    expect(mmss(605)).toBe("10:05");
    expect(mmss(3600)).toBe("60:00");
  });

  it("idle answers the bare app name", () => {
    expect(formatTabTitle({ appName: "Pomotivato", phaseLabel: "", remainingSec: null })).toBe(
      "Pomotivato",
    );
    expect(formatTabTitle({ appName: "Pomotivato", phaseLabel: "Работа", remainingSec: null })).toBe(
      "Pomotivato",
    );
  });

  it("a running phase carries the countdown FIRST (DF23 tab truncation)", () => {
    expect(
      formatTabTitle({ appName: "Pomotivato", phaseLabel: "Работа", remainingSec: 1450 }),
    ).toBe("24:10 Работа · Pomotivato");
  });
});
