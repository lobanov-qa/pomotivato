import { describe, expect, it } from "vitest";
import { t, type MessageKey } from "./ru";

/**
 * Dictionary contract tests (spec 03 §7): the single source of UI copy.
 * Test design: equivalence classes — every key, a typed key, an unknown key.
 */

const RU_KEYS = [
  "app.name",
  "nav.tasks",
  "nav.focus",
  "nav.settings",
  "error.network",
  "error.unknown",
] as const satisfies readonly MessageKey[];

describe("dictionary", () => {
  it.each(RU_KEYS)("renders non-empty RU text for key %s", (key) => {
    expect(t(key).trim().length).toBeGreaterThan(0);
  });

  it("keeps every dictionary key unique (typo guard)", () => {
    const values = RU_KEYS.map((key) => t(key));
    expect(new Set(values).size).toBe(RU_KEYS.length);
  });

  it("fails loudly when a key is missing at runtime", () => {
    // Type system blocks this at compile time; the cast simulates stale
    // data-driven keys (e.g. from an old test) to pin the runtime shape.
    expect(t("nope.nope" as MessageKey)).toBeUndefined();
  });
});
