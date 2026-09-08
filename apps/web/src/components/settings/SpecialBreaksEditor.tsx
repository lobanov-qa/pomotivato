/**
 * Special-breaks editor (spec 05 §3.3): up to 3 rows of HH:MM + minutes +
 * label, add/remove buttons. Controlled by the settings draft — the row
 * draft is plain state here, the server clamps (V13).
 */

import { Plus, Trash2 } from "lucide-react";
import type { SpecialBreakDto } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n/ru";

const MAX_BREAKS = 3;

interface Props {
  breaks: SpecialBreakDto[];
  onChange: (breaks: SpecialBreakDto[]) => void;
}

export function SpecialBreaksEditor({ breaks, onChange }: Props) {
  function patchRow(index: number, changes: Partial<SpecialBreakDto>): void {
    onChange(breaks.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  return (
    <div className="flex flex-col gap-2" data-testid="settings.special-breaks">
      {breaks.map((row, index) => (
        <div
          key={index}
          className="grid grid-cols-[88px_1fr_1fr_auto] items-center gap-2"
          data-testid={`settings.special-break-${index}`}
        >
          <Input
            type="time"
            aria-label={t("settings.sb-at")}
            data-testid={`settings.special-break-${index}-at`}
            value={row.at}
            onChange={(e) => patchRow(index, { at: e.target.value })}
          />
          <Input
            type="number"
            min={5}
            max={120}
            aria-label={t("settings.sb-minutes")}
            data-testid={`settings.special-break-${index}-min`}
            value={row.duration_min}
            onChange={(e) =>
              patchRow(index, {
                duration_min: Math.min(120, Math.max(0, Number(e.target.value) || 0)),
              })
            }
          />
          <Input
            aria-label={t("settings.sb-label")}
            data-testid={`settings.special-break-${index}-label`}
            value={row.label}
            maxLength={40}
            placeholder={t("settings.sb-label-placeholder")}
            onChange={(e) => patchRow(index, { label: e.target.value })}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t("settings.sb-remove")}
            data-testid={`settings.special-break-${index}-remove`}
            onClick={() => onChange(breaks.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {breaks.length < MAX_BREAKS && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          data-testid="settings.special-break-add"
          onClick={() =>
            onChange([...breaks, { at: "13:00", duration_min: 30, label: "" }])
          }
        >
          <Plus className="mr-1 h-4 w-4" />
          {t("settings.sb-add")}
        </Button>
      )}
    </div>
  );
}
