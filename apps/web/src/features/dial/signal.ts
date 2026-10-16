/**
 * Timer signal (A21/§22, spec 07 §10.10; DF33 shape picker, E4c-UX 5/5):
 * a WebAudio signal planned on the AUDIO CLOCK, not on an interval.
 * Background tabs throttle setInterval to about one call per minute, but a
 * scheduled oscillator still fires on time — so when a phase begins (its
 * `remaining_sec` is known from the SSE frame), the signal is parked at
 * `ctx.currentTime + remaining`.
 *
 * DF33 (author 15.10): the old two short beeps (~0.5 s) were missed too
 * often. The signal is now a ~2 s event in one of five synthesized shapes
 * (settings.ui.signal_kind); every shape keeps the same contract: pure
 * scheduling against AudioContextLike, cancelable nodes, nothing before the
 * first user gesture. The server stores the choice; the browser owns all
 * sound — no audio assets enter the repo.
 *
 * Browser autoplay law (§10.10 p.1): nothing may sound before the first
 * user gesture, so the AudioContext is created in the Start handler
 * (`attach`) and later schedules reuse it. The settings preview plays on a
 * click — clicks are gestures too. Out of scope by spec: OS push, sound
 * when the whole app is minimized, tray icon.
 */

import type { SignalKind } from "@/api/client";

export type ScheduledSignal = {
  osc: { stop: (when: number) => void };
};

export interface AudioContextLike {
  readonly currentTime: number;
  readonly destination: unknown;
  resume?: () => Promise<void>;
  createOscillator: () => {
    connect: (dest: unknown) => void;
    start: (when: number) => void;
    stop: (when: number) => void;
    frequency: {
      value: number;
      setValueAtTime: (value: number, when: number) => void;
      linearRampToValueAtTime: (value: number, when: number) => void;
    };
    type: string;
  };
  createGain: () => {
    connect: (dest: unknown) => void;
    gain: {
      value: number;
      setValueAtTime: (value: number, when: number) => void;
      linearRampToValueAtTime: (value: number, when: number) => void;
      exponentialRampToValueAtTime: (value: number, when: number) => void;
    };
  };
}

/** One oscillator + envelope, scheduled at `when`. The cancel unit. */
function voice(
  ctx: AudioContextLike,
  when: number,
  {
    type = "sine",
    freq,
    peak = 0.6,
    attack = 0.008,
    length = 0.5,
    decay = "exp",
    slideTo,
  }: {
    type?: string;
    freq: number;
    peak?: number;
    attack?: number;
    length?: number;
    decay?: "exp" | "lin" | "hold";
    slideTo?: number; // frequency ramp target across the whole voice
  },
): ScheduledSignal {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  if (slideTo !== undefined) {
    osc.frequency.setValueAtTime(freq, when);
    osc.frequency.linearRampToValueAtTime(slideTo, when + length);
  }
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.linearRampToValueAtTime(peak, when + attack);
  if (decay === "exp") gain.gain.exponentialRampToValueAtTime(0.0001, when + length);
  else if (decay === "lin") gain.gain.linearRampToValueAtTime(0.0001, when + length);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(when);
  osc.stop(when + length + 0.02);
  return { osc };
}

/** A bell strike: the fundamental plus two inharmonic partials decaying. */
function bell(ctx: AudioContextLike, when: number, base: number, length: number): ScheduledSignal[] {
  const partials: [number, number][] = [
    [1, 0.5],
    [1.26, 0.22],
    [1.5, 0.12],
  ];
  return partials.map(([mult, peak]) => voice(ctx, when, { freq: base * mult, peak, length }));
}

// The five shapes, all ~2 s at full scale, all pure scheduling (DF33):
//   bell-trill   three bell strikes overlapping (classic alarm clock)
//   siren        one sawtooth sweeping 600..1050 Hz three times
//   pulse-alarm  nine square beeps like an electronic timer
//   rising-tone  one sine swelling from quiet to loud, then it stops
//   chime-melody a major arpeggio of soft bells (the "live sample" shape,
//                synthesized — no audio files ship with the app)
const GENERATORS: Record<SignalKind, (ctx: AudioContextLike, when: number) => ScheduledSignal[]> =
  {
    "bell-trill": (ctx, when) =>
      [0, 0.6, 1.2].flatMap((offset) => bell(ctx, when + offset, 880, 0.7)),
    siren: (ctx, when) => {
      // up-down sweeps: 6 ramps of 1/3 s each over two seconds
      const nodes: ScheduledSignal[] = [];
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(600, when);
      for (let leg = 0; leg < 6; leg++) {
        const target = leg % 2 === 0 ? 1050 : 600;
        osc.frequency.linearRampToValueAtTime(target, when + (leg + 1) / 3);
      }
      gain.gain.setValueAtTime(0.0001, when);
      gain.gain.linearRampToValueAtTime(0.3, when + 0.02); // saw is harsh: lower peak
      gain.gain.exponentialRampToValueAtTime(0.0001, when + 2.0);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(when);
      osc.stop(when + 2.02);
      nodes.push({ osc });
      return nodes;
    },
    "pulse-alarm": (ctx, when) =>
      Array.from({ length: 9 }, (_, i) =>
        voice(ctx, when + i * 0.225, { type: "square", freq: 784, peak: 0.5, length: 0.1 }),
      ),
    "rising-tone": (ctx, when) => [
      voice(ctx, when, { freq: 660, peak: 0.9, attack: 1.7, length: 1.9, decay: "lin" }),
    ],
    "chime-melody": (ctx, when) =>
      [659.25, 783.99, 987.77, 1318.51].flatMap((freq, i) =>
        bell(ctx, when + i * 0.42, freq, 0.6),
      ),
  };

export const DEFAULT_SIGNAL_KIND: SignalKind = "bell-trill";

/** Play the chosen shape starting at `when` (audio-clock time). */
export function playSignal(
  kind: SignalKind,
  ctx: AudioContextLike,
  when: number,
): ScheduledSignal[] {
  const generate = GENERATORS[kind] ?? GENERATORS[DEFAULT_SIGNAL_KIND];
  return generate(ctx, when);
}

/** The browser's AudioContext when the runtime has one (tests/jsdom: no). */
export function defaultAudioContext(): AudioContextLike | null {
  // The DOM type carries more than our minimal contract needs; the cast
  // pins the structural subset the module actually uses.
  return typeof AudioContext === "undefined"
    ? null
    : (new AudioContext() as unknown as AudioContextLike);
}

/**
 * One-shot preview for the settings screen (DF33): the click that lands
 * here is itself the autoplay gesture. A single reusable context keeps
 * repeated clicks cheap; without an AudioContext (SSR/tests) it no-ops.
 */
let previewCtx: AudioContextLike | null | undefined;
export function previewSignal(kind: SignalKind): void {
  if (previewCtx === undefined) previewCtx = defaultAudioContext();
  if (!previewCtx) return;
  void previewCtx.resume?.().catch(() => undefined);
  playSignal(kind, previewCtx, previewCtx.currentTime + 0.05);
}

export class TimerSignal {
  private ctx: AudioContextLike | null = null;
  private pending: ScheduledSignal[] = [];

  /** Call from the Start button's handler — the gesture that unlocks
   * audio (autoplay policy, §10.10 p.1). Repeatable and idempotent. */
  attach(factory: () => AudioContextLike | null = defaultAudioContext): void {
    if (this.ctx === null) this.ctx = factory();
    void this.ctx?.resume?.().catch(() => undefined);
  }

  /** Park the signal at `remainingSec` from the audio clock's now. */
  schedule(remainingSec: number, kind: SignalKind = DEFAULT_SIGNAL_KIND): void {
    if (!this.ctx || remainingSec <= 0) return;
    this.cancel();
    this.pending = playSignal(kind, this.ctx, this.ctx.currentTime + remainingSec);
  }

  /** Drop a parked signal: the frozen remaining is no longer a deadline. */
  cancel(): void {
    for (const node of this.pending) {
      try {
        node.osc.stop(0);
      } catch {
        /* already finished — stopping a stopped node is legal noise */
      }
    }
    this.pending = [];
  }

  /** Test seam: whether the gesture already happened. */
  get attached(): boolean {
    return this.ctx !== null;
  }
}
