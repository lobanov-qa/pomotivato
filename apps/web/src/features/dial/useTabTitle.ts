/**
 * useTabTitle (spec 07 §10.14): the one DOM touch. Formatting lives in
 * tabTitle.ts as a pure function, so this hook is thin glue — and the
 * test floor asserts the function, never document.title.
 */

import { useEffect } from "react";
import { formatTabTitle } from "./tabTitle";

export function useTabTitle(
  appName: string,
  phaseLabel: string,
  remainingSec: number | null,
): void {
  useEffect(() => {
    const previous = document.title;
    document.title = formatTabTitle({ appName, phaseLabel, remainingSec });
    return () => {
      document.title = previous;
    };
  }, [appName, phaseLabel, remainingSec]);
}
