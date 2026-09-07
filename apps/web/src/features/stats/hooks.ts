/**
 * Re-render trigger when the theme flips (spec 04 §5, spec 03 §7): screens
 * read a fresh chartThemeFrom() per epoch change. MutationObserver on
 * html[data-theme] covers manual switching; matchMedia covers `auto`.
 */

import { useEffect, useState } from "react";

export function useThemeEpoch(): number {
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const bump = () => setEpoch((value) => value + 1);
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", bump);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", bump);
    };
  }, []);
  return epoch;
}
