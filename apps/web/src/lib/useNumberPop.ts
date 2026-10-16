import { useEffect, useRef } from "react";

/**
 * Д4 (wave Д): a number "pop" when its value changes — the modern skin
 * animates .number-pop (CSS owns the keyframes and the reduced-motion
 * law). The hook is skin-agnostic on purpose: the class is always applied,
 * only html[data-skin="modern"] gives it an animation, so minimal stays
 * untouched without branching in JS.
 *
 * Usage: attach the returned ref to an element wrapping the number.
 */
export function useNumberPop<T extends HTMLElement>(value: string | number): React.RefObject<T | null> {
  const ref = useRef<T | null>(null);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current === value) return;
    prev.current = value;
    const el = ref.current;
    if (!el) return;
    // Restart the CSS animation: remove, force a reflow, re-add.
    el.classList.remove("number-pop");
    void el.offsetWidth;
    el.classList.add("number-pop");
  }, [value]);
  return ref;
}
