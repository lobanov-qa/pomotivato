/**
 * /settings — the third screen of the MVP (spec 03 §2): session intervals
 * (work/break/long_break/long_break_every, auto_start_next) + ui key
 * (dial sectors ⚑ Q3, theme ⚑ Q9). Server is the source of truth; the
 * form is a draft that PUTs on "Сохранить" (no half-typed values leak).
 */

import { useState } from "react";
import type {
  SessionSettingsDto,
  SettingsBundleDto,
  ThemeName,
  UiSettingsDto,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import {
  usePutSessionSettings,
  usePutUiSettings,
  useUiSettings,
} from "@/features/settings/hooks";
import { t } from "@/i18n/ru";
import { cn } from "@/lib/utils";

type NumericSettingKey = {
  [K in keyof SessionSettingsDto]: SessionSettingsDto[K] extends number ? K : never;
}[keyof SessionSettingsDto];

const INTERVAL_FIELDS: {
  key: NumericSettingKey;
  labelKey: Parameters<typeof t>[0];
  min: number;
  max: number;
}[] = [
  { key: "work_min", labelKey: "settings.work", min: 1, max: 120 },
  { key: "break_min", labelKey: "settings.break", min: 1, max: 60 },
  { key: "long_break_min", labelKey: "settings.long-break", min: 1, max: 120 },
  { key: "long_break_every", labelKey: "settings.long-every", min: 2, max: 12 },
];

const THEMES: { value: ThemeName; labelKey: Parameters<typeof t>[0] }[] = [
  { value: "auto", labelKey: "settings.theme-auto" },
  { value: "light", labelKey: "settings.theme-light" },
  { value: "dark", labelKey: "settings.theme-dark" },
];

export function SettingsScreen() {
  const { data: settings, error: loadError } = useUiSettings();
  return settings ? (
    <SettingsForm key={JSON.stringify(settings)} settings={settings} />
  ) : loadError ? (
    <p className="text-sm text-danger">{t("error.network")}</p>
  ) : (
    <p className="text-sm text-muted-foreground">…</p>
  );
}

// Remounted (via key) whenever fresh server data arrives: the draft is
// plain local state seeded from props — no setState-in-effect dance.
function SettingsForm({ settings }: { settings: SettingsBundleDto }) {
  const putSession = usePutSessionSettings();
  const putUi = usePutUiSettings();
  const [sessionDraft, setSessionDraft] = useState<SessionSettingsDto>(settings.session);
  const [uiDraft, setUiDraft] = useState<UiSettingsDto>(settings.ui);

  const dirty =
    JSON.stringify(sessionDraft) !== JSON.stringify(settings.session) ||
    JSON.stringify(uiDraft) !== JSON.stringify(settings.ui);

  async function save(): Promise<void> {
    await Promise.all([
      putSession.mutateAsync(sessionDraft),
      putUi.mutateAsync(uiDraft),
    ]).catch(() => undefined);
  }

  return (
    <form
      className="mx-auto flex w-full max-w-md flex-col gap-6"
      data-testid="settings.screen"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <section className="flex flex-col gap-3" data-testid="settings.intervals">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {t("settings.section-intervals")}
        </h2>
        {INTERVAL_FIELDS.map(({ key, labelKey, min, max }) => (
          <div key={key} className="grid grid-cols-[1fr_96px] items-center gap-3">
            <Label htmlFor={`settings-${key}`}>{t(labelKey)}</Label>
            <Input
              id={`settings-${key}`}
              type="number"
              min={min}
              max={max}
              data-testid={`settings.field-${key}`}
              value={sessionDraft[key]}
              onChange={(e) =>
                setSessionDraft({
                  ...sessionDraft,
                  [key]: Math.min(max, Math.max(min, Number(e.target.value) || min)),
                })
              }
            />
          </div>
        ))}
        <label className="mt-1 flex items-center justify-between">
          <span className="text-sm">{t("settings.auto-start")}</span>
          <button
            type="button"
            role="switch"
            aria-checked={sessionDraft.auto_start_next}
            data-testid="settings.switch-auto-start"
            onClick={() =>
              setSessionDraft({ ...sessionDraft, auto_start_next: !sessionDraft.auto_start_next })
            }
            className={cn(
              "relative h-6 w-11 rounded-full border transition-colors",
              sessionDraft.auto_start_next ? "border-primary bg-primary" : "bg-muted",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 h-4.5 w-4.5 rounded-full bg-card shadow transition-all",
                sessionDraft.auto_start_next ? "left-6" : "left-0.5",
              )}
            />
          </button>
        </label>
      </section>

      <section className="flex flex-col gap-3" data-testid="settings.ui">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {t("settings.section-ui")}
        </h2>
        <div className="grid grid-cols-[1fr_96px] items-center gap-3">
          <Label htmlFor="settings-max-in-work">{t("settings.max-in-work")}</Label>
          <Input
            id="settings-max-in-work"
            type="number"
            min={1}
            max={12}
            data-testid="settings.field-max_in_work"
            value={uiDraft.max_in_work}
            onChange={(e) =>
              setUiDraft({
                ...uiDraft,
                max_in_work: Math.min(12, Math.max(1, Number(e.target.value) || 1)),
              })
            }
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label>{t("settings.theme")}</Label>
          <div className="flex gap-1" role="radiogroup" aria-label={t("settings.theme")}>
            {THEMES.map(({ value, labelKey }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={uiDraft.theme === value}
                data-testid={`settings.theme-${value}`}
                onClick={() => setUiDraft({ ...uiDraft, theme: value })}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-sm transition-colors",
                  uiDraft.theme === value
                    ? "border-primary bg-primary/10 font-medium"
                    : "hover:bg-muted",
                )}
              >
                {t(labelKey)}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="flex items-center gap-3">
        <Button type="submit" data-testid="settings.save" disabled={!dirty || putSession.isPending}>
          {t("settings.save")}
        </Button>
        {putSession.isError || putUi.isError ? (
          <span className="text-sm text-danger" data-testid="settings.error">
            {t("settings.error")}
          </span>
        ) : dirty ? (
          <span className="text-xs text-muted-foreground">{t("settings.dirty")}</span>
        ) : null}
      </div>
    </form>
  );
}
