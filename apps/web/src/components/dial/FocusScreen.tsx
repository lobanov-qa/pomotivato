/**
 * /focus — the dial screen (spec 03 §2): READ-ONLY for tasks by the
 * author's law. Buttons are session lifecycle only.
 *
 * Author's law (2026-09-06): the dial carries NO text labels; the current
 * task name is shown in FULL below the circle, and a numbered legend makes
 * it obvious which tasks the sectors hold and in what order. The rim is a
 * phase ring — one full revolution per phase (work or break), painting
 * nothing behind itself.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, SkipForward, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, type SessionDto } from "@/api/client";
import { Dial } from "@/components/dial/Dial";
import { Button } from "@/components/ui/button";
import { useTasks } from "@/features/kanban/hooks";
import { deriveSlots } from "@/features/kanban/planner";
import { useSessionEvents } from "@/features/dial/useSessionEvents";
import { type PhaseName } from "@/features/dial/geometry";
import { t } from "@/i18n/ru";

function today(): string {
  return new Date().toLocaleDateString("en-CA");
}

export function FocusScreen() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["status"], queryFn: api.getStatus, refetchInterval: 5000 });
  const sessionId: string | null = status.data?.active ? (status.data.session_id ?? null) : null;
  const { session, connected, anchorMs, refetch } = useSessionEvents(sessionId);
  const { tasks } = useTasks();

  // Local 1s tick between server events; the value is always derived from
  // the anchored remaining_sec, so a paused server freezes it honestly.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const remainingSec = useMemo(() => {
    if (!session || anchorMs === null) return 0;
    if (session.state !== "running") return session.remaining_sec; // paused: frozen
    const phase = session.phase;
    if (phase !== "work" && phase !== "break" && phase !== "long_break") {
      return session.remaining_sec;
    }
    return Math.max(
      0,
      session.remaining_sec - Math.max(0, Math.floor((now - anchorMs) / 1000)),
    );
  }, [session, anchorMs, now]);

  const sectors = session?.slots?.length ?? 0;
  const open = session?.timeline.find((seg) => seg.status === null) ?? null;
  const workDone =
    session?.timeline.filter((seg) => seg.status !== null && seg.phase === "work").length ?? 0;
  const isWork = session?.phase === "work";
  const sectorIndex = Math.max(
    0,
    Math.min(Math.max(sectors - 1, 0), workDone - (isWork ? 0 : 1)),
  );
  const sectorFraction =
    isWork && open ? 1 - remainingSec / Math.max(1, open.planned_min * 60) : isWork ? 0 : 1;
  // The rim is a PHASE ring: one revolution per phase, whatever its length.
  const phaseFraction = open ? 1 - remainingSec / Math.max(1, open.planned_min * 60) : 0;

  const titleOf = useMemo(() => {
    const byId = new Map(tasks.map((task) => [task.id, task.title]));
    return (taskId: string | null | undefined): string => (taskId ? byId.get(taskId) ?? "" : "");
  }, [tasks]);

  const currentTaskTitle = useMemo(() => {
    if (!session?.slots) return "";
    if (isWork) return titleOf(open?.task_id ?? session.slots[sectorIndex]?.task_id);
    // during a break: the task the NEXT sector belongs to (author's model)
    return titleOf(session.slots[workDone]?.task_id);
  }, [session, isWork, open, sectorIndex, workDone, titleOf]);

  const sectorTitles = useMemo(
    () => (session?.slots ?? []).map((slot) => titleOf(slot.task_id)),
    [session, titleOf],
  );

  const plannedToday = useMemo(
    () => deriveSlots(tasks.filter((task) => task.status === "doing")),
    [tasks],
  );

  async function act(verb: "start" | "pause" | "resume" | "stop" | "skip"): Promise<void> {
    try {
      if (verb === "start") {
        if (plannedToday.length === 0) return;
        const date = today();
        const plan = await api.getDayPlan(date).catch(() => null);
        const planId =
          plan?.id ?? (await api.putDayPlan({ id: `plan-${date}`, date, slots: plannedToday })).id;
        await api.startSession({ day_plan_id: planId });
      } else if (verb === "pause" && session) {
        await api.pauseSession(session.id);
      } else if (verb === "resume" && session) {
        await api.resumeSession(session.id);
      } else if (verb === "stop" && session) {
        await api.stopSession(session.id);
      } else if (verb === "skip" && session) {
        await api.skipBreak(session.id);
      }
    } finally {
      // Server is the authority: pull the fresh view immediately (the SSE
      // snapshot will confirm it, but the UI must not wait on the stream).
      void client.invalidateQueries({ queryKey: ["status"] });
      await refetch().catch(() => undefined);
    }
  }

  const running = Boolean(session && (session.state === "running" || session.state === "paused"));
  const isBreak = session?.phase === "break" || session?.phase === "long_break";
  const paused = session?.state === "paused";

  return (
    <div className="flex flex-col items-center gap-5" data-testid="dial.screen">
      {!connected && running && (
        <p className="text-xs text-warning" data-testid="dial.disconnected">
          {t("dial.disconnected")}
        </p>
      )}
      <Dial
        sectors={running ? sectors : plannedToday.length}
        phase={(session?.phase ?? null) as PhaseName | null}
        sectorIndex={sectorIndex}
        sectorFraction={Math.min(1, Math.max(0, sectorFraction))}
        phaseFraction={Math.min(1, Math.max(0, phaseFraction))}
        completedSectors={Math.min(sectors, workDone)}
        remainingSec={remainingSec}
        active={running}
      />
      {/* phase + FULL task name live outside the circle (author's law) */}
      <div className="flex flex-col items-center gap-1 text-center" data-testid="dial.info">
        <p
          className="text-xs uppercase tracking-[0.2em] text-muted-foreground"
          data-testid="dial.phase-label"
        >
          {paused
            ? t("dial.phase-paused")
            : session?.phase
              ? t(`dial.phase-${session.phase}` as "dial.phase-work")
              : t("dial.phase-idle")}
        </p>
        {running && currentTaskTitle && (
          <p className="max-w-md text-base font-medium" data-testid="dial.task-name">
            {!isWork && <span className="text-muted-foreground">{t("dial.next-task")} </span>}
            {currentTaskTitle}
          </p>
        )}
      </div>
      {paused && (
        <p className="text-sm text-muted-foreground" data-testid="dial.paused-hint">
          {t("dial.paused-hint")}
        </p>
      )}
      <div className="flex items-center gap-2">
        {!running && (
          <Button
            data-testid="dial.start-button"
            disabled={plannedToday.length === 0}
            onClick={() => void act("start")}
          >
            <Play className="h-4 w-4" />
            {t("dial.start")}
          </Button>
        )}
        {running && !paused && (
          <Button variant="secondary" data-testid="dial.pause-button" onClick={() => void act("pause")}>
            <Pause className="h-4 w-4" />
            {t("dial.pause")}
          </Button>
        )}
        {running && paused && (
          <Button data-testid="dial.resume-button" onClick={() => void act("resume")}>
            <Play className="h-4 w-4" />
            {t("dial.resume")}
          </Button>
        )}
        {running && isBreak && (
          <Button variant="outline" data-testid="dial.skip-break-button" onClick={() => void act("skip")}>
            <SkipForward className="h-4 w-4" />
            {t("dial.skip-break")}
          </Button>
        )}
        {running && (
          <Button variant="danger" data-testid="dial.stop-button" onClick={() => void act("stop")}>
            <Square className="h-4 w-4" />
            {t("dial.stop")}
          </Button>
        )}
      </div>
      {plannedToday.length === 0 && !running && (
        <p className="text-sm text-muted-foreground" data-testid="dial.no-plan">
          {t("dial.no-plan")}
        </p>
      )}
      {/* numbered sector legend: which tasks the dial holds, in order */}
      {running && sectorTitles.length > 0 && (
        <ol className="flex w-full max-w-md flex-col gap-1" data-testid="dial.legend">
          {sectorTitles.map((title, i) => (
            <li
              key={i}
              data-testid={`dial.legend-item-${i + 1}`}
              className={
                i === sectorIndex
                  ? "flex items-center gap-2 rounded-md border border-primary/50 bg-primary/10 px-3 py-1.5 text-sm"
                  : "flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm text-muted-foreground"
              }
            >
              <span className="font-mono text-xs">{i + 1}</span>
              <span className="truncate">{title}</span>
            </li>
          ))}
        </ol>
      )}
      {session && <ScoreBadge session={session} />}
      {/* no "В работе" list here: the funnel law makes doing == the dial,
          and the legend above already names every sector in full */}
    </div>
  );
}

function ScoreBadge({ session }: { session: SessionDto }) {
  if (session.average_score === null) return null;
  return (
    <p className="text-sm text-muted-foreground" data-testid="dial.score-badge">
      {t("dial.average-score")}:{" "}
      <span className="font-semibold text-foreground">{session.average_score.toFixed(1)}</span>
      {" · "}
      {session.reviews.length} {t("dial.reviews-count")}
    </p>
  );
}
