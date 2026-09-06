/**
 * SSE subscription for one session (spec 03 §4). The stream is the push
 * channel; every event merges its payload into the last full snapshot
 * (server truth). Reconnects are cheap: the first frame is always a fresh
 * snapshot, and a manual GET /sessions/{id} stays the catch-up fallback
 * (spec 03 §3 CATCH-UP: the browser never extrapolates state on its own).
 *
 * State is keyed by session id, so a late event from a dying stream can
 * never bleed into a new session's view (no setState in the effect body).
 */

import { useCallback, useEffect, useState } from "react";
import { api, type SessionDto } from "@/api/client";

export interface DialState {
  session: SessionDto | null;
  connected: boolean;
  /** Local ms timestamp when the last remaining_sec was server-fresh. */
  anchorMs: number | null;
  refetch: () => Promise<void>;
}

interface Keyed {
  key: string;
  session: SessionDto;
  anchorMs: number;
}

export function useSessionEvents(sessionId: string | null): DialState {
  const [snapshot, setSnapshot] = useState<Keyed | null>(null);
  const [connectedKey, setConnectedKey] = useState<string | null>(null);

  const refetch = useCallback(async (): Promise<void> => {
    if (!sessionId) return;
    const fresh = await api.getSession(sessionId);
    setSnapshot({ key: sessionId, session: fresh, anchorMs: Date.now() });
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let closed = false;
    const source = new EventSource(api.sessionEventsUrl(sessionId));

    const merge = (patch: Partial<SessionDto>, reanchor = false) =>
      setSnapshot((prev) =>
        prev && prev.key === sessionId
          ? {
              key: sessionId,
              session: { ...prev.session, ...patch },
              anchorMs: reanchor ? Date.now() : prev.anchorMs,
            }
          : prev,
      );

    source.addEventListener("snapshot", (event) => {
      setConnectedKey(sessionId);
      setSnapshot({
        key: sessionId,
        session: JSON.parse((event as MessageEvent).data) as SessionDto,
        anchorMs: Date.now(), // clock-skew anchor: remaining is fresh now
      });
    });
    source.addEventListener("phase_changed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as {
        phase: string | null;
        ends_at: string | null;
        remaining_sec: number;
      };
      merge(
        { phase: data.phase, phase_ends_at: data.ends_at, remaining_sec: data.remaining_sec },
        true,
      );
      // phase_changed carries no timeline: a fresh segment opened, so the
      // merged view would lose the open segment (the hand/rim freeze and
      // the review modal never fires). Refetch the full authoritative view.
      void refetch().catch(() => undefined);
    });
    source.addEventListener("segment_closed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as {
        segment_id: string;
        status: string;
      };
      // Cosmetic merge for a known segment; if the client somehow missed
      // its opening, the next phase_changed/snapshot refetch heals it.
      setSnapshot((prev) =>
        prev && prev.key === sessionId
          ? {
              ...prev,
              session: {
                ...prev.session,
                timeline: prev.session.timeline.map((seg) =>
                  seg.id === data.segment_id ? { ...seg, status: data.status } : seg,
                ),
              },
            }
          : prev,
      );
    });
    source.addEventListener("session_finished", (event) => {
      setSnapshot({
        key: sessionId,
        session: JSON.parse((event as MessageEvent).data) as SessionDto,
        anchorMs: Date.now(),
      });
      source.close(); // the server closed its side; stop reconnecting
      setConnectedKey(null);
    });
    source.onerror = () => {
      if (!closed) setConnectedKey(null); // EventSource retries on its own
    };
    // No seed GET: the server's first frame is always `snapshot` (spec 03
    // §4), which lands through the listener above — one source of truth.

    return () => {
      closed = true;
      source.close();
    };
  }, [sessionId, refetch]);

  const current = snapshot && snapshot.key === sessionId ? snapshot : null;
  return {
    session: current?.session ?? null,
    connected: sessionId !== null && connectedKey === sessionId,
    anchorMs: current?.anchorMs ?? null,
    refetch,
  };
}
