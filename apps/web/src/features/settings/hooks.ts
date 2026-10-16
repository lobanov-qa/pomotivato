/**
 * UI settings shared plumbing (spec 03 §5 ⚑ Q3/Q6/Q9): one query for the
 * settings bundle, a ThemeSync component that mirrors ui.theme onto the
 * <html data-theme> attribute (the CSS owns the actual palettes).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  api,
  type SessionSettingsDto,
  type SettingsBundleDto,
  type UiSettingsDto,
} from "@/api/client";

export const SETTINGS_KEY = ["settings"] as const;

export function useUiSettings() {
  return useQuery({ queryKey: SETTINGS_KEY, queryFn: api.getSettings });
}

export function usePutSessionSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (settings: SessionSettingsDto) => api.putSessionSettings(settings),
    onSuccess: () => void client.invalidateQueries({ queryKey: SETTINGS_KEY }),
  });
}

export function usePutUiSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ui: UiSettingsDto) => api.putUiSettings(ui),
    onSuccess: () => void client.invalidateQueries({ queryKey: SETTINGS_KEY }),
  });
}

/** Applies the server theme and skin to <html>; no-ops until settings
 * arrive. Д1: data-skin joins data-theme — the same mirror law, the CSS
 * under html[data-skin="modern"] owns the modern palette (wave Д). */
export function ThemeSync() {
  const { data } = useUiSettings();
  useEffect(() => {
    if (data) {
      document.documentElement.dataset.theme = data.ui.theme;
      document.documentElement.dataset.skin = data.ui.skin;
    }
  }, [data]);
  return null;
}

export type { SettingsBundleDto };
