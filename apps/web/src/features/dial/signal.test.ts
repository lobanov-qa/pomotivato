import { describe, expect, it, vi } from "vitest";
import { TimerSignal, type AudioContextLike, playBeeps } from "./signal";
import { formatTabTitle, mmss } from "./tabTitle";

/**
 * Timer signal and tab title (spec 07 §1 p.22, §10.10, §10.14). §10.14
 * is law here: the title is asserted as a FUNCTION, never as document.title
 * (e2e owns the DOM later); the signal is asserted against a fake
 * AudioContext — scheduling on the audio clock is the contract.
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
        frequency: { value: 0 },
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
      },
    }),
  };
}

describe("playBeeps (audio-clock scheduling)", () => {
  it("parks two beeps at `when` and `when + gap`", () => {
    const ctx = fakeCtx();

    const nodes = playBeeps(ctx, 40);

    expect(nodes).toHaveLength(2);
    const starts = ctx.calls.filter((call) => call[0] === "osc-start");
    expect(starts).toEqual([
      ["osc-start", 40],
      ["osc-start", 40.35],
    ]);
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

  it("schedule parks the chime at currentTime + remaining", () => {
    const ctx = fakeCtx(10);
    const signal = new TimerSignal();
    signal.attach(() => ctx);

    signal.schedule(600);

    expect(ctx.calls.filter((call) => call[0] === "osc-start")).toEqual([
      ["osc-start", 610],
      ["osc-start", 610.35],
    ]);
  });

  it("re-scheduling cancels the parked chime (a new phase, not two deadlines)", () => {
    const ctx = fakeCtx(0);
    const signal = new TimerSignal();
    signal.attach(() => ctx);

    signal.schedule(1200);
    signal.schedule(300);

    // the first pair got stop(0) calls before the second pair was parked
    const stops = ctx.calls.filter((call) => call[0] === "osc-stop");
    expect(stops).toContainEqual(["osc-stop", 0]);
    expect(stops[stops.length - 1]).not.toEqual(["osc-stop", 0]); // fresh beeps scheduled on
  });

  it("cancel drops a parked chime without scheduling anything", () => {
    const ctx = fakeCtx(0);
    const signal = new TimerSignal();
    signal.attach(() => ctx);
    signal.schedule(900);
    ctx.calls.length = 0;

    signal.cancel();

    expect(ctx.calls).toEqual([
      ["osc-stop", 0],
      ["osc-stop", 0],
    ]);
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

  it("a running phase carries the countdown", () => {
    expect(
      formatTabTitle({ appName: "Pomotivato", phaseLabel: "Работа", remainingSec: 1450 }),
    ).toBe("Pomotivato · Работа 24:10");
  });
});
