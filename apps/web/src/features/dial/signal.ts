/**
 * Timer signal (A21/§22, spec 07 §10.10): a WebAudio chime planned on the
 * AUDIO CLOCK, not on an interval. Background tabs throttle setInterval to
 * about one call per minute, but a scheduled oscillator still fires on
 * time — so when a phase begins (its `remaining_sec` is known from the
 * SSE frame), the chime is parked at `ctx.currentTime + remaining`.
 *
 * Browser autoplay law (§10.10 p.1): nothing may sound before the first
 * user gesture, so the AudioContext is created in the Start handler
 * (`attach`) and later schedules reuse it. Out of scope by spec: OS push,
 * sound when the whole app is minimized, tray icon.
 */

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
    frequency: { value: number };
    type: string;
  };
  createGain: () => {
    connect: (dest: unknown) => void;
    gain: {
      value: number;
      setValueAtTime: (value: number, when: number) => void;
      linearRampToValueAtTime: (value: number, when: number) => void;
    };
  };
}

/** Two short sine beeps at `when` and `when + gap`. Returns the scheduled
 * oscillators so the caller can cancel a far-future chime (pause/stop). */
export function playBeeps(
  ctx: AudioContextLike,
  when: number,
  { freq = 880, gap = 0.35, length = 0.18 }: { freq?: number; gap?: number; length?: number } = {},
): ScheduledSignal[] {
  const nodes: ScheduledSignal[] = [];
  for (const offset of [0, gap]) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, when + offset);
    gain.gain.linearRampToValueAtTime(0.6, when + offset + 0.01);
    gain.gain.linearRampToValueAtTime(0.0001, when + offset + length);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(when + offset);
    osc.stop(when + offset + length + 0.02);
    nodes.push({ osc });
  }
  return nodes;
}

/** The browser's AudioContext when the runtime has one (tests/jsdom: no). */
export function defaultAudioContext(): AudioContextLike | null {
    // The DOM type carries more than our minimal contract needs; the cast
  // pins the structural subset the module actually uses.
  return typeof AudioContext === "undefined" ? null : (new AudioContext() as unknown as AudioContextLike);
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

  /** Park the chime at `remainingSec` from the audio clock's now. */
  schedule(remainingSec: number): void {
    if (!this.ctx || remainingSec <= 0) return;
    this.cancel();
    this.pending = playBeeps(this.ctx, this.ctx.currentTime + remainingSec);
  }

  /** Drop a parked chime: the frozen remaining is no longer a deadline. */
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
